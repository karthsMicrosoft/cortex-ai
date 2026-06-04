import uuid

import pytest
from sqlalchemy import select

from app.models.note import Note
from app.models.note_link import NoteLink
from app.models.tag import Tag, note_tags
from app.models.user import User
from app.services import semantic_links
from app.services.semantic_links import (
    RelinkResult,
    composite_score,
    extract_salient_phrases,
    passes_floor,
    phrase_jaccard,
    rebuild_user_links,
    relink_single_note,
    tag_jaccard,
    title_jaccard,
)


@pytest.fixture(autouse=True)
def clear_relink_rate_limit():
    semantic_links._last_run.clear()
    yield
    semantic_links._last_run.clear()


def test_tag_jaccard_empty_both_zero():
    assert tag_jaccard(set(), set()) == 0.0


def test_tag_jaccard_disjoint_zero():
    assert tag_jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_tag_jaccard_identical_one():
    assert tag_jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_tag_jaccard_partial():
    assert tag_jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_title_jaccard_empty_or_none_zero():
    assert title_jaccard(None, "hello") == 0.0
    assert title_jaccard("", "hello") == 0.0
    assert title_jaccard("hello", None) == 0.0
    assert title_jaccard("hello", "") == 0.0


def test_title_jaccard_stopwords_removed():
    assert title_jaccard("the cat in the hat", "a cat with a hat") == 1.0


def test_title_jaccard_partial():
    assert title_jaccard("morning run stats", "evening run report") == pytest.approx(1 / 5)


def test_composite_score_weights():
    # All-ones still saturates to 1.0 (weights sum to 1.0).
    assert composite_score(sem=1, tag=1, title=1, phrase=1) == 1.0
    assert composite_score(sem=0, tag=0, title=0, phrase=0) == 0.0
    # Pure-semantic component contributes WEIGHT_SEMANTIC (0.55 in Round 33).
    assert composite_score(sem=1, tag=0, title=0, phrase=0) == pytest.approx(0.55)
    # Pure-phrase component contributes WEIGHT_PHRASE (0.20 in Round 33).
    assert composite_score(sem=0, tag=0, title=0, phrase=1) == pytest.approx(0.20)
    # Backwards-compat: 3-arg call (no phrase) still works, drops to 0 default.
    assert composite_score(sem=1, tag=0, title=0) == pytest.approx(0.55)


def test_passes_floor_semantic_anchor():
    # Sem floor lowered to 0.60 in Round 33.
    assert passes_floor(sem=0.6, tag=0.0, title=0.0, phrase=0.0) is True


def test_passes_floor_tag_anchor():
    assert passes_floor(sem=0.0, tag=0.5, title=0.0, phrase=0.0) is True


def test_passes_floor_title_anchor():
    assert passes_floor(sem=0.0, tag=0.0, title=0.5, phrase=0.0) is True


def test_passes_floor_phrase_anchor():
    # Round 33: a single literal-phrase Jaccard hit (>=0.4) is enough to anchor
    # a link, even when every other signal is zero. This is the fix for the
    # "Film Meetup" bug — two notes that share the exact capitalized phrase
    # link up even when their embeddings + tags differ.
    assert passes_floor(sem=0.0, tag=0.0, title=0.0, phrase=0.4) is True


def test_passes_floor_below_all():
    assert passes_floor(sem=0.3, tag=0.3, title=0.3, phrase=0.3) is False


def test_passes_floor_backwards_compatible_three_args():
    # Older callers that don't pass `phrase` get the conservative answer.
    assert passes_floor(sem=0.65, tag=0.0, title=0.0) is True
    assert passes_floor(sem=0.0, tag=0.0, title=0.0) is False


# ---------------------------------------------------------------------------
# Round 33: phrase signal — extract_salient_phrases + phrase_jaccard
# ---------------------------------------------------------------------------


def test_extract_salient_phrases_picks_multiword_capitalized():
    # "Film Meetup" appears in the body verbatim — the user's bug-report case.
    content = "Went to the Film Meetup last night and we discussed Project Cortex briefly."
    phrases = extract_salient_phrases(content)
    assert "film meetup" in phrases
    assert "project cortex" in phrases


def test_extract_salient_phrases_skips_single_word_caps():
    # "Today" / "I" at sentence start would be noisy; we only capture 2+ words.
    content = "Today I went to Park. Yesterday it Rained."
    phrases = extract_salient_phrases(content)
    assert "today" not in phrases
    assert "park" not in phrases
    assert "rained" not in phrases


def test_extract_salient_phrases_includes_hashtags():
    content = "Random thoughts about #film-meetup and #project_cortex"
    phrases = extract_salient_phrases(content)
    assert "film-meetup" in phrases
    assert "project_cortex" in phrases


def test_extract_salient_phrases_includes_title_and_tags():
    # Round 33: title + tags are NOT included in the phrase set (they're
    # already captured by title_jaccard / tag_jaccard). Confirm the kwargs
    # are accepted for backwards compat but ignored.
    phrases = extract_salient_phrases(
        content="body without capitalized phrases",
        title="My Big Idea",
        tag_names={"film-meetup", "weekend"},
    )
    assert "my big idea" not in phrases
    assert "film-meetup" not in phrases
    assert "weekend" not in phrases


def test_extract_salient_phrases_title_kwarg_ignored():
    # Even when the body is empty, title shouldn't pollute the phrase set.
    phrases = extract_salient_phrases(
        content=None, title="Sun Morning Run", tag_names={"a"},
    )
    assert phrases == set()


def test_extract_salient_phrases_lowercases():
    content = "FILM MEETUP was great"
    # All-caps multi-word still matches (regex allows any alphanumeric after
    # the leading uppercase). The match is lowercased on the way into the
    # phrase set so casing variants ("Film Meetup", "FILM MEETUP", "film
    # meetup") all collapse to the same key.
    phrases = extract_salient_phrases(content)
    assert phrases == {"film meetup"}


def test_extract_salient_phrases_handles_empty_inputs():
    assert extract_salient_phrases(None) == set()
    assert extract_salient_phrases("") == set()
    assert extract_salient_phrases("   ") == set()
    assert extract_salient_phrases(None, title=None, tag_names=set()) == set()


def test_phrase_jaccard_basic():
    assert phrase_jaccard(set(), set()) == 0.0
    assert phrase_jaccard({"film meetup"}, {"film meetup"}) == 1.0
    assert phrase_jaccard({"a", "b"}, {"a"}) == pytest.approx(0.5)
    # Disjoint phrases (no overlap whatsoever) -> 0
    assert phrase_jaccard({"film meetup"}, {"sunday run"}) == 0.0


def test_film_meetup_repro_two_notes_link():
    """Reproduces the user's bug-report case from Round 33.

    Two notes both contain the literal phrase 'Film Meetup' in their bodies
    but talk about wildly different ideas. Pre-Round-33 the cosine
    similarity stayed below the 0.65 floor, the tags went 'movies' vs
    'social-life', and no link was created. Round 33: the phrase signal
    catches the explicit shared phrase and anchors the link via the
    strong-single-signal path (phrase >= STRONG_PHRASE).
    """
    from app.services.semantic_links import link_qualifies

    a_content = "At the Film Meetup we argued whether Lynch is overrated. Took notes."
    a_phrases = extract_salient_phrases(a_content)
    b_content = "Saw an AI demo at the Film Meetup. Could use it for my journaling app."
    b_phrases = extract_salient_phrases(b_content)

    assert "film meetup" in a_phrases
    assert "film meetup" in b_phrases

    # Body-only phrase extraction is NOT diluted by unrelated title/tag
    # tokens, so the Jaccard reflects the actual literal-phrase overlap.
    phrase = phrase_jaccard(a_phrases, b_phrases)
    assert phrase >= 0.5, (
        f"Two notes whose only shared multi-word phrase is 'Film Meetup' "
        f"must produce phrase_jaccard >= 0.5. Got {phrase}."
    )

    # The strong-single-signal path (Path B) is what fires here:
    # phrase >= STRONG_PHRASE (0.5) is enough on its own. Composite alone
    # would be 0.55*0.4 + 0.20*1.0 = 0.42, below the 0.55 threshold —
    # without Path B the link would still be missed.
    sem = 0.4
    composite = composite_score(sem=sem, tag=0.0, title=0.0, phrase=phrase)
    assert link_qualifies(
        sem=sem, tag=0.0, title=0.0, phrase=phrase,
        composite=composite, threshold=0.55,
    ) is True, "Strong-single-signal anchor must fire for the Film Meetup case."


def _embedding_for_db(db_session):
    dialect = db_session.get_bind().dialect.name
    if dialect == "postgresql":
        return [0.1] * 1536
    return "[0.1]"


async def _make_user(db_session):
    user = User(
        email=f"semantic_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        display_name="Semantic",
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_note(db_session, user, *, title="Note", tags=None, embedding=None):
    note = Note(
        user_id=user.id,
        content=title or "content",
        title=title,
        category="Ideas",
        embedding=embedding,
    )
    db_session.add(note)
    await db_session.flush()

    for tag_name in tags or []:
        existing = await db_session.execute(
            select(Tag).where(Tag.user_id == user.id, Tag.name == tag_name)
        )
        tag = existing.scalar_one_or_none()
        if tag is None:
            tag = Tag(user_id=user.id, name=tag_name, is_auto=True)
            db_session.add(tag)
            await db_session.flush()
        await db_session.execute(
            note_tags.insert().values(note_id=note.id, tag_id=tag.id)
        )
    await db_session.flush()
    return note


async def _links_for_source(db_session, source_id):
    result = await db_session.execute(
        select(NoteLink).where(
            NoteLink.source_note_id == source_id,
            NoteLink.link_type == "semantic",
        )
    )
    return result.scalars().all()


@pytest.mark.asyncio
async def test_relink_single_note_no_embedding_returns_empty(db_session):
    user = await _make_user(db_session)
    note = await _make_note(db_session, user, title="Source", embedding=None)

    result = await relink_single_note(db_session, note)

    assert result == RelinkResult()


@pytest.mark.asyncio
async def test_relink_single_note_semantic_peer_creates_link(db_session, monkeypatch):
    user = await _make_user(db_session)
    embedding = _embedding_for_db(db_session)
    source = await _make_note(db_session, user, title="Source", embedding=embedding)
    peer = await _make_note(db_session, user, title="Peer", embedding=embedding)

    async def fake_candidates(db, note, **kwargs):
        return [{"id": peer.id, "title": peer.title, "content": None, "sem": 0.9}]

    monkeypatch.setattr(semantic_links, "_fetch_vector_candidates", fake_candidates)

    result = await relink_single_note(db_session, source)
    links = await _links_for_source(db_session, source.id)

    assert result.created == 1
    assert result.updated == 0
    assert len(links) == 1
    assert links[0].target_note_id == peer.id
    # Round 33: when the single-signal anchor path wins, the stored score
    # is max(composite, all signals) so pure-cosine 0.9 still surfaces as
    # ~0.9 in Brain View, not the lower composite of 0.495.
    assert links[0].similarity_score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_relink_single_note_only_floor_passing_peer_linked(db_session, monkeypatch):
    user = await _make_user(db_session)
    embedding = _embedding_for_db(db_session)
    source = await _make_note(db_session, user, title="Source", tags=["shared"], embedding=embedding)
    floor_peer = await _make_note(db_session, user, title="Floor peer", tags=["shared"], embedding=embedding)
    no_floor_peer = await _make_note(db_session, user, title="No floor peer", embedding=embedding)

    async def fake_candidates(db, note, **kwargs):
        return [
            {"id": floor_peer.id, "title": floor_peer.title, "content": None, "sem": 0.4},
            {"id": no_floor_peer.id, "title": no_floor_peer.title, "content": None, "sem": 0.4},
        ]

    monkeypatch.setattr(semantic_links, "_fetch_vector_candidates", fake_candidates)

    result = await relink_single_note(db_session, source, sem_threshold=0.2)
    links = await _links_for_source(db_session, source.id)

    assert result.created == 1
    assert {link.target_note_id for link in links} == {floor_peer.id}


@pytest.mark.asyncio
async def test_relink_single_note_rerun_upserts_updates_existing(db_session, monkeypatch):
    user = await _make_user(db_session)
    embedding = _embedding_for_db(db_session)
    source = await _make_note(db_session, user, title="Source", embedding=embedding)
    peer = await _make_note(db_session, user, title="Peer", embedding=embedding)
    sem_value = 0.9

    async def fake_candidates(db, note, **kwargs):
        return [{"id": peer.id, "title": peer.title, "content": None, "sem": sem_value}]

    monkeypatch.setattr(semantic_links, "_fetch_vector_candidates", fake_candidates)

    first = await relink_single_note(db_session, source)
    sem_value = 0.95
    second = await relink_single_note(db_session, source)
    links = await _links_for_source(db_session, source.id)

    assert first.created == 1
    assert first.updated == 0
    assert second.created == 0
    assert second.updated == 1
    assert len(links) == 1
    # Round 33: max(composite, sem) wins for strong-single-signal links.
    assert links[0].similarity_score == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_rebuild_user_links_rate_limit_skips_recent_run(db_session):
    user = await _make_user(db_session)

    first = await rebuild_user_links(db_session, user.id)
    second = await rebuild_user_links(db_session, user.id)

    assert first.skipped_recent is False
    assert second.skipped_recent is True
    assert second.duration_ms == 0


@pytest.mark.asyncio
async def test_rebuild_user_links_empty_notes_zero_counters(db_session):
    user = await _make_user(db_session)

    result = await rebuild_user_links(db_session, user.id)

    assert result.created == 0
    assert result.updated == 0
    assert result.skipped_recent is False
