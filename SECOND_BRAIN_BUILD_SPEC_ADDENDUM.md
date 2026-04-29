# CORTEX — Second Brain Application
# SPEC ADDENDUM v1.1

> **Note**: This addendum extends `SECOND_BRAIN_BUILD_SPEC.md` with two new features
> inspired by competitive analysis of Wispr Flow (personal dictionary) and
> VoicePal (shadow reader).
>
> Both features fit within Phase 2 of the MVP plan and align with Cortex's
> design philosophy of frictionless capture and AI augmentation.

**Phase Markers**: Each feature is structured with the same Agent Teams
phases (Requirements -> Design -> Critique -> Coding -> Review) so Claude Code
Agent Teams can phase-detect and resume from anywhere.

---

# FEATURE 1: PERSONAL DICTIONARY (STT Vocabulary Boost)

**Inspiration**: Wispr Flow's personal dictionary feature that dramatically
improves STT accuracy for names, jargon, and domain-specific terms.
**Effort**: ~1 day | **Priority**: P1 | **MVP Phase**: 2

---

## [REQUIREMENTS] F1.1 — Functional Requirements

### FR-7: Personal Dictionary

| ID | Requirement | Priority |
|---|---|---|
| FR-7.1 | User can add custom terms to a personal vocabulary | P1 |
| FR-7.2 | Each term has a type (name, music_term, technical, place, acronym) | P1 |
| FR-7.3 | Optional pronunciation hint for each term (e.g. 'Karthik = car-thick') | P2 |
| FR-7.4 | Terms loaded into Azure Speech PhraseListGrammar before each STT session | P1 |
| FR-7.5 | User can edit, delete, and view all dictionary terms | P1 |
| FR-7.6 | Dictionary is per-user and synced across devices | P1 |
| FR-7.7 | Bulk import from CSV/JSON | P2 |

### Use Cases

- Karthik adds 'arpeggio', 'Phrygian mode', 'pentatonic' as music terms -> STT correctly transcribes them in voice notes
- Karthik adds 'Daniel Anvar', 'Sangya Singh' as names -> STT no longer mishears them
- Karthik adds 'pgvector', 'CODE framework', 'Cosmos DB' as technical terms

### Acceptance Criteria

- [ ] User can add a term in < 10 seconds from settings page
- [ ] Next voice recording uses the updated dictionary
- [ ] STT accuracy on dictionary terms is measurably higher (test with 10 known terms)
- [ ] Dictionary entries are stored in PostgreSQL and survive app restart

---

## [DESIGN] F1.2 — Architecture

### Database Schema (Append to existing schema)

```sql
-- ============================================
-- USER VOCABULARY (Personal Dictionary)
-- ============================================
CREATE TABLE user_vocabulary (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    term VARCHAR(200) NOT NULL,
    term_type VARCHAR(30) NOT NULL DEFAULT 'general'
        CHECK (term_type IN ('name', 'music_term', 'technical', 'place', 'acronym', 'general')),
    pronunciation_hint VARCHAR(500),
    boost_weight FLOAT DEFAULT 1.0,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, term)
);

CREATE INDEX idx_vocabulary_user ON user_vocabulary(user_id);
CREATE INDEX idx_vocabulary_type ON user_vocabulary(user_id, term_type);
```

### API Endpoints

```yaml
GET    /api/dictionary                  # List all terms (filterable by type)
POST   /api/dictionary                  # Add a new term
PUT    /api/dictionary/{id}             # Update term
DELETE /api/dictionary/{id}             # Remove term
POST   /api/dictionary/bulk             # Bulk import (JSON array)
GET    /api/dictionary/export           # Export as JSON
```

### Backend: SQLAlchemy Model

```python
# backend/app/models/vocabulary.py
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
import uuid

class UserVocabulary(Base):
    __tablename__ = 'user_vocabulary'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    term = Column(String(200), nullable=False)
    term_type = Column(String(30), default='general')
    pronunciation_hint = Column(String(500), nullable=True)
    boost_weight = Column(Float, default=1.0)
    usage_count = Column(Integer, default=0)
```

### Backend: FastAPI Endpoints

```python
# backend/app/api/dictionary.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from uuid import UUID

router = APIRouter(prefix='/api/dictionary', tags=['dictionary'])
MAX_TERMS_PER_USER = 2000

class VocabularyTerm(BaseModel):
    term: str = Field(..., min_length=1, max_length=200)
    term_type: str = Field(default='general')
    pronunciation_hint: str | None = None
    boost_weight: float = Field(default=1.0, ge=0.0, le=2.0)

@router.get('')
async def list_terms(
    term_type: str | None = None,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(UserVocabulary).where(UserVocabulary.user_id == user_id)
    if term_type:
        query = query.where(UserVocabulary.term_type == term_type)
    result = await db.execute(query.order_by(UserVocabulary.usage_count.desc()))
    return result.scalars().all()

@router.post('', status_code=201)
async def add_term(
    payload: VocabularyTerm,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Enforce hard limit
    count = await db.scalar(
        select(func.count()).select_from(UserVocabulary)
        .where(UserVocabulary.user_id == user_id)
    )
    if count >= MAX_TERMS_PER_USER:
        raise HTTPException(400, f'Dictionary limit of {MAX_TERMS_PER_USER} reached')

    vocab = UserVocabulary(user_id=user_id, **payload.dict())
    db.add(vocab)
    try:
        await db.commit()
        await db.refresh(vocab)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, 'Term already exists')
    return vocab

@router.delete('/{term_id}', status_code=204)
async def delete_term(
    term_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await db.execute(
        delete(UserVocabulary).where(
            UserVocabulary.id == term_id,
            UserVocabulary.user_id == user_id
        )
    )
    await db.commit()

@router.post('/bulk', status_code=201)
async def bulk_import(
    terms: list[VocabularyTerm],
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if len(terms) > 500:
        raise HTTPException(400, 'Bulk import limited to 500 terms per request')
    inserted = 0
    for t in terms:
        vocab = UserVocabulary(user_id=user_id, **t.dict())
        db.add(vocab)
        try:
            await db.commit()
            inserted += 1
        except IntegrityError:
            await db.rollback()
    return {'inserted': inserted, 'total': len(terms)}
```

### Azure Speech Integration (Phrase List)

Azure Speech Service supports **PhraseListGrammar** which boosts recognition
accuracy for specified terms. Limit: ~500 phrases per session.

```python
# backend/app/services/speech.py
import azure.cognitiveservices.speech as speechsdk
from sqlalchemy import select
from app.models.vocabulary import UserVocabulary

async def load_user_phrase_list(
    recognizer: speechsdk.SpeechRecognizer,
    user_id,
    db,
    max_phrases: int = 500
) -> int:
    """Load the user's personal dictionary into the STT recognizer.

    Returns: count of phrases loaded.
    """
    result = await db.execute(
        select(UserVocabulary)
        .where(UserVocabulary.user_id == user_id)
        .order_by(UserVocabulary.usage_count.desc())
        .limit(max_phrases)
    )
    terms = result.scalars().all()
    if not terms:
        return 0

    phrase_list = speechsdk.PhraseListGrammar.from_recognizer(recognizer)
    for term in terms:
        phrase_list.addPhrase(term.term)
        if term.pronunciation_hint:
            phrase_list.addPhrase(term.pronunciation_hint)
    return len(terms)

async def increment_term_usage(content: str, user_id, db):
    """After STT, increment usage_count for terms found in transcription."""
    result = await db.execute(
        select(UserVocabulary).where(UserVocabulary.user_id == user_id)
    )
    terms = result.scalars().all()
    content_lower = content.lower()
    for term in terms:
        if term.term.lower() in content_lower:
            term.usage_count += 1
    await db.commit()
```

### WebSocket Voice Handler — Updated to Use Dictionary

```python
# backend/app/api/voice.py — UPDATED
@router.websocket('/api/voice/stream')
async def voice_stream(websocket, token: str, db = Depends(get_db)):
    user_id = validate_ws_token(token)
    await websocket.accept()

    speech_config = speechsdk.SpeechConfig(...)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config, audio_config=audio_config
    )

    # *** NEW: Load user's personal dictionary ***
    phrase_count = await load_user_phrase_list(recognizer, user_id, db)
    logger.info(f'Loaded {phrase_count} phrases for user {user_id}')

    # ... rest of existing WebSocket logic unchanged
```

### Frontend: Personal Dictionary UI

```typescript
// frontend/src/components/PersonalDictionary.tsx
import { useState, useEffect } from 'react';
import { Plus, X, Mic } from 'lucide-react';

interface VocabTerm {
  id: string;
  term: string;
  term_type: 'name' | 'music_term' | 'technical' | 'place' | 'acronym' | 'general';
  pronunciation_hint?: string;
  usage_count: number;
}

const TYPE_COLORS = {
  name: 'bg-blue-900',
  music_term: 'bg-purple-900',
  technical: 'bg-green-900',
  place: 'bg-amber-900',
  acronym: 'bg-rose-900',
  general: 'bg-slate-700',
};

export function PersonalDictionary() {
  const [terms, setTerms] = useState<VocabTerm[]>([]);
  const [newTerm, setNewTerm] = useState('');
  const [newType, setNewType] = useState<VocabTerm['term_type']>('general');

  useEffect(() => { loadTerms(); }, []);

  const loadTerms = async () => {
    const res = await fetch('/api/dictionary', {
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    setTerms(await res.json());
  };

  const addTerm = async () => {
    if (!newTerm.trim()) return;
    await fetch('/api/dictionary', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAccessToken()}`
      },
      body: JSON.stringify({ term: newTerm.trim(), term_type: newType })
    });
    setNewTerm('');
    loadTerms();
  };

  const removeTerm = async (id: string) => {
    await fetch(`/api/dictionary/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    loadTerms();
  };

  return (
    <section className='bg-slate-900 rounded-2xl p-6'>
      <div className='flex items-center gap-2 mb-4'>
        <Mic className='w-5 h-5 text-indigo-400' />
        <h2 className='text-xl font-semibold'>Personal Dictionary</h2>
      </div>
      <p className='text-slate-400 text-sm mb-4'>
        Add names, jargon, or terms you use often to improve voice transcription.
      </p>

      <div className='flex gap-2 mb-4'>
        <input
          value={newTerm}
          onChange={(e) => setNewTerm(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addTerm()}
          placeholder='e.g. Phrygian mode, Karthik, pgvector'
          className='flex-1 bg-slate-800 rounded-lg px-3 py-2 text-sm'
        />
        <select
          value={newType}
          onChange={(e) => setNewType(e.target.value as VocabTerm['term_type'])}
          className='bg-slate-800 rounded-lg px-3 py-2 text-sm'
        >
          <option value='general'>General</option>
          <option value='name'>Name</option>
          <option value='music_term'>Music</option>
          <option value='technical'>Technical</option>
          <option value='place'>Place</option>
          <option value='acronym'>Acronym</option>
        </select>
        <button onClick={addTerm} className='bg-indigo-600 px-3 rounded-lg'>
          <Plus className='w-4 h-4' />
        </button>
      </div>

      <div className='flex flex-wrap gap-2'>
        {terms.map(t => (
          <span key={t.id}
                className={`${TYPE_COLORS[t.term_type]} pl-3 pr-1 py-1 rounded-full text-xs flex items-center gap-1`}>
            {t.term}
            <button onClick={() => removeTerm(t.id)}
                    className='hover:bg-black/20 rounded-full p-0.5'>
              <X className='w-3 h-3' />
            </button>
          </span>
        ))}
      </div>
    </section>
  );
}
```

---

## [CRITIQUE] F1.3 — Validation & Mitigations

### Concerns

| Concern | Mitigation |
|---|---|
| Azure Speech caps at ~500 phrases per session | Order by usage_count DESC, only load top 500 |
| Term might collide with common English words | Optional `boost_weight` slider (0.0-2.0); default 1.0 |
| User dumps a CSV with 10K terms | Server-side limit on dictionary size (2000 terms total) |
| Privacy: dictionary contains personal data (names) | Same encryption as notes (Postgres at-rest); never logged |
| Dictionary changes don't take effect immediately | Force reload of phrase list on every WebSocket connection |

### Required Mitigations

1. Hard limit of 2000 dictionary terms per user (enforced on POST)
2. Phrase list refreshed on every voice session (no caching across sessions)
3. Bulk import endpoint validates each term (length, no special chars)
4. usage_count incremented after STT to keep most-used terms in the top-500

---

## [CODING] F1.4 — Files to Add/Modify

```
backend/
  app/
    models/
      vocabulary.py              # NEW: UserVocabulary SQLAlchemy model
    schemas/
      dictionary.py              # NEW: Pydantic schemas
    api/
      dictionary.py              # NEW: CRUD endpoints
      voice.py                   # MODIFY: load phrase list before STT
    services/
      speech.py                  # MODIFY: add load_user_phrase_list()
  alembic/versions/
    002_add_user_vocabulary.py   # NEW: migration

frontend/
  src/
    api/
      dictionary.ts              # NEW: API client
    pages/
      SettingsPage.tsx           # MODIFY: include PersonalDictionary section
    components/
      PersonalDictionary.tsx     # NEW: dictionary UI component
```

### Implementation Order

1. Create Alembic migration for `user_vocabulary` table
2. Add SQLAlchemy model
3. Implement FastAPI CRUD endpoints (5 endpoints)
4. Update `services/speech.py` with `load_user_phrase_list`
5. Update WebSocket handler to call phrase list loader
6. Build SettingsPage with PersonalDictionary component
7. Wire up frontend API client
8. Test: add term, record voice, verify accuracy improvement

---

## [REVIEW] F1.5 — Acceptance Criteria

- [ ] User can add a term and see it in the list within 1 second
- [ ] STT recognizes added terms in next voice recording (manual test with 5 known-difficult terms)
- [ ] Term usage_count increments after STT
- [ ] Hard limit of 2000 terms enforced
- [ ] Bulk import works for up to 500 terms in one request
- [ ] Settings page renders dictionary on mobile and desktop
- [ ] DELETE endpoint removes term and updates UI
- [ ] Azure Speech logs show phrase list loaded on each WS connection

---
---
# FEATURE 2: SHADOW READER (Conversational Refinement)

**Inspiration**: VoicePal's Shadow Reader feature that asks intelligent
follow-up questions to deepen captured thoughts.
**Effort**: ~2-3 days | **Priority**: P1 | **MVP Phase**: 2

> **Design Philosophy Alignment**: 'AI augments thinking, does not replace it.'
> Shadow Reader doesn't generate content FOR the user — it helps the user think
> deeper through gentle, well-crafted questions.

---

## [REQUIREMENTS] F2.1 — Functional Requirements

### FR-8: Shadow Reader

| ID | Requirement | Priority |
|---|---|---|
| FR-8.1 | After capture, AI generates 1-2 follow-up questions tailored to the note | P1 |
| FR-8.2 | Questions are dismissible (user can skip without penalty) | P0 |
| FR-8.3 | Question style varies by category (Music vs Journal vs Ideas) | P1 |
| FR-8.4 | User answers via voice or text | P1 |
| FR-8.5 | Answer is appended to note as 'Reflection' section | P1 |
| FR-8.6 | Embedding is regenerated after answer is added | P1 |
| FR-8.7 | Global toggle in settings to enable/disable Shadow Reader | P0 |
| FR-8.8 | Smart trigger: only asks for substantive notes (>= 50 words) | P1 |
| FR-8.9 | User can mark a category as 'never ask' (e.g. quick fitness logs) | P2 |

### Use Cases

**Example 1 — Music Note**
- Voice: 'Just hummed a melody in D minor with a descending bassline'
- Shadow Reader asks:
  - 'What emotion does this melody evoke for you?'
  - 'What instrument do you imagine playing this?'
- User answers: 'It feels melancholy, like rain on glass. I imagine cello with soft piano.'
- Note becomes: original content + Reflection section with the deepening

**Example 2 — Journal Entry**
- Voice: 'Had a tough conversation with my manager today about scope'
- Shadow Reader asks:
  - 'What feeling underlies the difficulty?'
  - 'What outcome would feel right to you?'

**Example 3 — Idea**
- Voice: 'What if Cortex had a daily reflection ritual?'
- Shadow Reader asks:
  - 'What is the smallest version of this you could try this week?'
  - 'Who else might benefit from this?'

### Acceptance Criteria

- [ ] Questions appear within 3 seconds of note creation
- [ ] Questions are dismissible with one tap
- [ ] Off-toggle in settings works immediately (no questions ever appear)
- [ ] Answer persists to note and updates embedding
- [ ] Per-category opt-out works

---

## [DESIGN] F2.2 — Architecture

### Pipeline Integration

Shadow Reader runs as a NEW stage between Capture (Stage 1) and Organize (Stage 2):

```
Stage 0: Ingest (STT)
       v
Stage 1: CAPTURE (clean text)
       v
Stage 1.5: REFLECT (Shadow Reader)  <- NEW
  - Trigger check (>=50 words? user enabled? category not opted-out?)
  - Generate 1-2 questions via GPT-4o-mini
  - Push questions to UI via polling
  - Wait for user response (or skip after 60s)
       v
Stage 2: ORGANIZE (tag, embed, link)
```

### Database Schema Updates

```sql
-- Add to existing users table
ALTER TABLE users
ADD COLUMN shadow_reader_enabled BOOLEAN DEFAULT TRUE,
ADD COLUMN shadow_reader_disabled_categories JSONB DEFAULT '[]'::jsonb;

-- Add to existing notes table
ALTER TABLE notes
ADD COLUMN shadow_reader_questions JSONB DEFAULT NULL,
ADD COLUMN shadow_reader_answer TEXT DEFAULT NULL,
ADD COLUMN shadow_reader_status VARCHAR(20) DEFAULT 'pending'
    CHECK (shadow_reader_status IN ('pending', 'asked', 'answered', 'dismissed', 'skipped'));
```

### API Endpoints

```yaml
GET    /api/notes/{id}/shadow-reader              # Get current questions for a note
POST   /api/notes/{id}/shadow-reader/answer       # Submit answer
POST   /api/notes/{id}/shadow-reader/dismiss      # Dismiss without answering
PUT    /api/users/me/shadow-reader/settings       # Update enabled / disabled categories
```

### Backend Pipeline Implementation

```python
# backend/app/pipeline/shadow_reader.py
from typing import List
import json

# Category-specific question prompts
CATEGORY_PROMPTS = {
    'Music': (
        'You are a thoughtful music collaborator. Read this music idea and ask 1-2 '
        'gentle questions that help the user develop the idea further. Focus on emotion, '
        'instrumentation, lyrical themes, or musical structure. Keep questions short and warm.'
    ),
    'Journal': (
        'You are a wise, compassionate listener. Read this journal entry and ask 1-2 '
        'gentle questions that help the user reflect deeper. Focus on feelings beneath '
        'the surface, what the person really needs, or what truth they might be avoiding. '
        'Be warm, never clinical.'
    ),
    'Ideas': (
        'You are a thoughtful creative partner. Read this idea and ask 1-2 sharp '
        'questions that help the user clarify or develop it. Focus on the smallest '
        'next step, hidden assumptions, or who might benefit. Be direct but kind.'
    ),
    'Fitness': (
        'You are an encouraging fitness coach. Read this fitness note and ask 1 short '
        'question about how the body felt, what was the hardest part, or what comes next.'
    ),
    'Spiritual': (
        'You are a contemplative companion. Read this spiritual reflection and ask 1-2 '
        'gentle questions that invite deeper presence or insight. Avoid religious specificity.'
    ),
    'Learning': (
        'You are a curious teacher. Read this learning note and ask 1-2 questions '
        'that help the user connect this to what they already know, or apply it.'
    ),
}

MIN_WORDS_FOR_TRIGGER = 50

async def should_trigger_shadow_reader(note, user) -> bool:
    """Decide whether to run Shadow Reader for this note."""
    if not user.shadow_reader_enabled:
        return False
    if note.category in (user.shadow_reader_disabled_categories or []):
        return False
    word_count = len(note.content.split())
    if word_count < MIN_WORDS_FOR_TRIGGER:
        return False
    return True

async def generate_questions(note, openai_client) -> List[str]:
    """Generate 1-2 thoughtful follow-up questions for the note."""
    category_prompt = CATEGORY_PROMPTS.get(note.category, CATEGORY_PROMPTS['Ideas'])
    full_prompt = (
        f"{category_prompt}\n\n"
        f"Note content:\n{note.content}\n\n"
        'Return a JSON object with a single key "questions" containing an array '
        'of 1-2 question strings. Make each question concise (under 15 words). '
        'Do not number them.'
    )
    response = await openai_client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': full_prompt}],
        max_tokens=200,
        temperature=0.7,
        response_format={'type': 'json_object'}
    )
    result = json.loads(response.choices[0].message.content)
    questions = result.get('questions', [])
    return questions[:2]  # Cap at 2

async def run_shadow_reader_stage(note, user, openai_client, db) -> None:
    """Stage 1.5: Reflect — generate questions if appropriate."""
    if not await should_trigger_shadow_reader(note, user):
        note.shadow_reader_status = 'skipped'
        await db.commit()
        return
    questions = await generate_questions(note, openai_client)
    note.shadow_reader_questions = questions
    note.shadow_reader_status = 'asked'
    await db.commit()

async def merge_answer_into_note(note, answer: str, openai_client, db) -> None:
    """After user answers, append reflection to note content and regenerate embedding."""
    note.shadow_reader_answer = answer
    note.shadow_reader_status = 'answered'
    note.content = f'{note.content}\n\n--- Reflection ---\n{answer}'
    # Regenerate embedding to include the reflection
    embed_response = await openai_client.embeddings.create(
        model='text-embedding-3-small',
        input=note.content
    )
    note.embedding = embed_response.data[0].embedding
    await db.commit()
```

### FastAPI Endpoints

```python
# backend/app/api/shadow_reader.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from uuid import UUID

router = APIRouter(prefix='/api/notes', tags=['shadow_reader'])

class ShadowReaderAnswer(BaseModel):
    answer: str

@router.get('/{note_id}/shadow-reader')
async def get_shadow_reader_questions(
    note_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db = Depends(get_db)
):
    """Poll for shadow reader questions for a given note."""
    note = await get_note_or_404(db, note_id, user_id)
    return {
        'status': note.shadow_reader_status,
        'questions': note.shadow_reader_questions or []
    }

@router.post('/{note_id}/shadow-reader/answer')
async def answer_shadow_reader(
    note_id: UUID,
    payload: ShadowReaderAnswer,
    user_id: UUID = Depends(get_current_user),
    db = Depends(get_db),
    openai_client = Depends(get_openai)
):
    note = await get_note_or_404(db, note_id, user_id)
    if note.shadow_reader_status != 'asked':
        raise HTTPException(409, 'Shadow reader not in asked state')
    await merge_answer_into_note(note, payload.answer, openai_client, db)
    return {'status': 'answered', 'updated_content': note.content}

@router.post('/{note_id}/shadow-reader/dismiss')
async def dismiss_shadow_reader(
    note_id: UUID,
    user_id: UUID = Depends(get_current_user),
    db = Depends(get_db)
):
    note = await get_note_or_404(db, note_id, user_id)
    note.shadow_reader_status = 'dismissed'
    await db.commit()
    return {'status': 'dismissed'}
```

### Frontend: Shadow Reader Prompt Component

```typescript
// frontend/src/components/ShadowReaderPrompt.tsx
import { useState, useEffect } from 'react';
import { Sparkles, Mic, X, Send } from 'lucide-react';

interface Props {
  noteId: string;
  onComplete?: () => void;
}

export function ShadowReaderPrompt({ noteId, onComplete }: Props) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [status, setStatus] = useState<'loading' | 'asked' | 'hidden'>('loading');
  const [answer, setAnswer] = useState('');

  // Poll for questions (max 5 attempts, 1s interval)
  useEffect(() => {
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      const res = await fetch(`/api/notes/${noteId}/shadow-reader`, {
        headers: { Authorization: `Bearer ${getAccessToken()}` }
      });
      const data = await res.json();
      if (data.status === 'asked' && data.questions.length > 0) {
        setQuestions(data.questions);
        setStatus('asked');
        clearInterval(interval);
      } else if (
        data.status === 'skipped' ||
        data.status === 'dismissed' ||
        attempts >= 5
      ) {
        setStatus('hidden');
        clearInterval(interval);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [noteId]);

  const submitAnswer = async () => {
    if (!answer.trim()) return;
    await fetch(`/api/notes/${noteId}/shadow-reader/answer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAccessToken()}`
      },
      body: JSON.stringify({ answer: answer.trim() })
    });
    setStatus('hidden');
    onComplete?.();
  };

  const dismiss = async () => {
    await fetch(`/api/notes/${noteId}/shadow-reader/dismiss`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    setStatus('hidden');
    onComplete?.();
  };

  if (status !== 'asked') return null;

  return (
    <div className='fixed bottom-0 left-0 right-0 z-40 animate-slide-up'>
      <div className='bg-gradient-to-t from-slate-900 to-slate-800 border-t border-indigo-500/30 rounded-t-3xl p-5 shadow-2xl'>
        <div className='flex items-start justify-between mb-3'>
          <div className='flex items-center gap-2'>
            <Sparkles className='w-4 h-4 text-indigo-400' />
            <span className='text-sm text-slate-300'>Want to go deeper?</span>
          </div>
          <button onClick={dismiss} className='text-slate-500 hover:text-slate-300'>
            <X className='w-4 h-4' />
          </button>
        </div>

        <div className='space-y-2 mb-4'>
          {questions.map((q, idx) => (
            <p key={idx} className='text-base text-slate-100 leading-relaxed'>
              {q}
            </p>
          ))}
        </div>

        <div className='flex gap-2'>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder='Reflect briefly... (or skip)'
            rows={2}
            className='flex-1 bg-slate-950 rounded-xl px-3 py-2 text-sm resize-none'
          />
          <div className='flex flex-col gap-2'>
            <button onClick={submitAnswer} className='bg-indigo-600 p-2 rounded-xl hover:bg-indigo-500'>
              <Send className='w-4 h-4' />
            </button>
            <button className='bg-slate-700 p-2 rounded-xl'>
              <Mic className='w-4 h-4' />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

### Settings UI for Shadow Reader Toggle

```typescript
// frontend/src/components/ShadowReaderSettings.tsx
export function ShadowReaderSettings() {
  const [enabled, setEnabled] = useState(true);
  const [disabledCategories, setDisabledCategories] = useState<string[]>([]);
  const ALL_CATEGORIES = ['Music','Fitness','Journal','Ideas','Spiritual','Learning'];

  const toggleCategory = (cat: string) => {
    setDisabledCategories(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    );
  };

  const save = async () => {
    await fetch('/api/users/me/shadow-reader/settings', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAccessToken()}`
      },
      body: JSON.stringify({ enabled, disabled_categories: disabledCategories })
    });
  };

  return (
    <section className='bg-slate-900 rounded-2xl p-6'>
      <h2 className='text-xl font-semibold mb-2'>Shadow Reader</h2>
      <p className='text-slate-400 text-sm mb-4'>
        After capture, get gentle questions that help you go deeper into your thinking.
      </p>
      <label className='flex items-center justify-between mb-4'>
        <span>Enable Shadow Reader</span>
        <input type='checkbox'
               checked={enabled}
               onChange={e => setEnabled(e.target.checked)}
               className='w-5 h-5 rounded' />
      </label>
      {enabled && (
        <>
          <p className='text-xs text-slate-500 mb-2'>Skip questions for these categories:</p>
          <div className='flex flex-wrap gap-2 mb-4'>
            {ALL_CATEGORIES.map(cat => (
              <button key={cat}
                      onClick={() => toggleCategory(cat)}
                      className={`px-3 py-1 rounded-full text-xs ${
                        disabledCategories.includes(cat)
                          ? 'bg-slate-700 line-through text-slate-500'
                          : 'bg-indigo-900 text-indigo-200'
                      }`}>
                {cat}
              </button>
            ))}
          </div>
        </>
      )}
      <button onClick={save} className='bg-indigo-600 px-4 py-2 rounded-lg text-sm'>
        Save
      </button>
    </section>
  );
}
```

---

## [CRITIQUE] F2.3 — Validation & Mitigations

### Concerns

| Concern | Mitigation |
|---|---|
| Annoyance: questions on every note feel intrusive | Smart trigger (>= 50 words) + per-category opt-out + global toggle |
| Token cost: extra GPT-4o-mini call per note | ~$0.0001 extra per note (negligible). Skip for short notes. |
| Bad questions could feel mechanical | Category-specific prompts with warm tone. Iterate on prompts. |
| User in a rush, doesn't want a prompt | Modal slides up softly, dismissible with one tap |
| Embedding regeneration on answer adds latency | Run async after answer is saved; UI returns immediately |
| Privacy: sensitive journal entries get sent to LLM | Same as existing pipeline; document in privacy policy |

### Required Mitigations

1. **Always dismissible** — X button visible at all times
2. **Smart trigger** — >= 50 words AND user-enabled AND category not opted-out
3. **Soft animation** — slide up from bottom, never modal-block the screen
4. **Category-aware prompts** — different tone for Music vs Journal vs Ideas
5. **Question cap** — max 2 questions, max 15 words each
6. **Background processing** — embedding regeneration happens after UI returns
7. **Per-note dismiss** — dismissing one note's questions does not affect future notes

---

## [CODING] F2.4 — Files to Add/Modify

```
backend/
  app/
    pipeline/
      shadow_reader.py           # NEW: Stage 1.5 Reflect logic
      processor.py               # MODIFY: insert shadow_reader stage
    api/
      shadow_reader.py           # NEW: 3 endpoints
      users.py                   # MODIFY: settings endpoint
    models/
      user.py                    # MODIFY: add shadow_reader fields
      note.py                    # MODIFY: add shadow_reader fields
  alembic/versions/
    003_add_shadow_reader.py     # NEW: migration

frontend/
  src/
    api/
      shadowReader.ts            # NEW: API client
    components/
      ShadowReaderPrompt.tsx     # NEW: bottom-sheet UI
      ShadowReaderSettings.tsx   # NEW: settings section
    pages/
      NoteDetailPage.tsx         # MODIFY: render ShadowReaderPrompt after capture
      SettingsPage.tsx           # MODIFY: include settings section
    styles/
      animations.css             # MODIFY: add slide-up keyframe
```

### Implementation Order

1. Alembic migration: add columns to `users` and `notes`
2. Update SQLAlchemy models
3. Implement `pipeline/shadow_reader.py` with category prompts
4. Update main `pipeline/processor.py` to call Stage 1.5 between Capture and Organize
5. Implement 3 FastAPI endpoints
6. Implement settings endpoint (PUT /api/users/me/shadow-reader/settings)
7. Build `ShadowReaderPrompt` component with poll logic
8. Add settings section to SettingsPage
9. Wire into NoteDetailPage so it appears after capture
10. Iterate on prompt quality with real notes (test all 6 categories)

---

## [REVIEW] F2.5 — Acceptance Criteria

- [ ] Questions appear within 3 seconds for notes >= 50 words
- [ ] No questions for notes < 50 words
- [ ] Off-toggle in settings prevents all questions
- [ ] Per-category opt-out works (e.g. disable Fitness, still works for Music)
- [ ] Dismiss button hides prompt and updates status to 'dismissed'
- [ ] Submit answer appends 'Reflection' section to note content
- [ ] Embedding is regenerated after answer (verify by re-running similar search)
- [ ] Voice input for answer works on mobile
- [ ] All 6 categories produce contextually appropriate questions
- [ ] Prompt component does not block UI / is dismissible at any time

---
---

# UPDATED COST & MVP IMPACT

## Cost Impact

| Feature | Additional Tokens/Note | Additional Cost/mo (1000 notes) |
|---|---|---|
| Personal Dictionary | 0 (no LLM call) | $0 |
| Shadow Reader (questions) | ~300 in + 100 out | ~$0.10 |
| Shadow Reader (re-embed on answer) | ~300 | ~$0.01 |
| **Total additional cost** | | **~$0.11/month** |

> Negligible cost increase. Total stays well under $150/month.

## Updated MVP Phase 2 Plan

Insert these tasks into Phase 2 (after item 28 in section 4.2 of the main spec):

```
Phase 2 (Updated):
  22. Backend: Daily/weekly summary generation
  23. Backend: Scheduled task for auto-summaries
  24. Backend: Note links API (graph data)
  25. Backend: Pattern detection endpoint
  26. Frontend: Insights page
  27. Frontend: Brain View page
  28. Frontend: Processing status badges
  --- NEW ---
  29. Backend: Personal Dictionary CRUD + Azure phrase list integration (~1 day)
  30. Frontend: Settings page with Personal Dictionary section
  31. Backend: Shadow Reader pipeline stage + endpoints (~2 days)
  32. Frontend: ShadowReaderPrompt component + settings (~1 day)
  --- /NEW ---
  33. Backend: WebSocket real-time STT streaming
  34. Frontend: Real-time transcription feedback
```

---

**END OF SPEC ADDENDUM v1.1**

*Both features are fully designed, costed, and ready for Claude Code Agent Teams to implement.*

*Generated for Karthik Subramanian | Cortex — Second Brain | April 2026*