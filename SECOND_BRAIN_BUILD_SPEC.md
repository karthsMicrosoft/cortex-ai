# CORTEX — Second Brain Application
# Claude Code Agent Teams Build Specification

---

## PROJECT METADATA

| Field | Value |
|---|---|
| **Project Name** | Cortex — AI-Powered Second Brain |
| **Author** | Karthik Subramanian |
| **Budget** | $150/month (Azure) |
| **Target Platform** | Mobile-first PWA (Progressive Web App) |
| **Deployment** | Azure Container Apps + Azure Static Web Apps |
| **Repository Structure** | Monorepo (`/frontend`, `/backend`, `/infra`, `/docs`) |
| **Framework** | CODE (Capture, Organize, Distill, Express) |
| **Design Philosophy** | Frictionless capture > everything. AI augments thinking, does not replace it. System feels like an extension of memory, not a database. |

---

## IMPORTANT: READ THIS FIRST

This specification is designed for **Claude Code Agent Teams** using the experimental multi-agent workflow:

```
Requirements → Design → Critique → Coding → Review
```

Each section is tagged with phase markers. **Smart phase detection** should resume from where work left off.

### How to Use This Spec
1. Feed this entire file to Claude Code Agent Teams
2. The agents will process each phase sequentially
3. Each phase has explicit acceptance criteria
4. Do NOT skip phases — each builds on the previous
5. All Azure resources use the `westus2` region unless specified otherwise

---

# ═══════════════════════════════════════════════════════
# PHASE 1: REQUIREMENTS
# ═══════════════════════════════════════════════════════

## [REQUIREMENTS] 1.1 — Product Vision

Cortex is a **personal AI-powered knowledge management system** optimized for:

- **Voice-first capture**: 1-tap record → auto-transcribe → auto-structure → store
- **Multi-modal input**: Voice, text, images
- **AI-assisted thinking**: Auto-tagging, summarization, pattern detection, creative generation
- **Semantic retrieval**: Natural language queries across all personal knowledge
- **Music ideation**: Preserve and organize musical ideas (humming, melodies, whistling)

This is NOT a note-taking app. It is a **personal RAG system over your life data**.

---

## [REQUIREMENTS] 1.2 — Functional Requirements

### FR-1: Input Modes
| ID | Requirement | Priority |
|---|---|---|
| FR-1.1 | Voice capture with 1-tap record button | P0 |
| FR-1.2 | Auto-transcription using Azure Speech-to-Text (streaming) | P0 |
| FR-1.3 | Preserve original audio files in Azure Blob Storage | P0 |
| FR-1.4 | Text input (manual notes, journaling) | P0 |
| FR-1.5 | Image upload with OCR via Azure AI Vision | P1 |

### FR-2: AI Processing Pipeline (CODE Framework)
| ID | Requirement | Priority |
|---|---|---|
| FR-2.1 | **Capture**: Clean raw transcription into structured note | P0 |
| FR-2.2 | **Organize**: Auto-tag, auto-categorize, generate embeddings | P0 |
| FR-2.3 | **Organize**: Link semantically related notes | P1 |
| FR-2.4 | **Distill**: Daily/weekly summaries | P1 |
| FR-2.5 | **Distill**: Extract key ideas, highlight patterns | P1 |
| FR-2.6 | **Express**: Generate song ideas from voice notes | P2 |
| FR-2.7 | **Express**: Generate practice plans from fitness logs | P2 |
| FR-2.8 | **Express**: Generate reflections from journal entries | P2 |

### FR-3: Search System
| ID | Requirement | Priority |
|---|---|---|
| FR-3.1 | Semantic search using embeddings (pgvector) | P0 |
| FR-3.2 | Natural language queries ("Find my melody ideas from last week") | P0 |
| FR-3.3 | Filter by category, tags, date range | P0 |
| FR-3.4 | Hybrid search (keyword + semantic) | P1 |

### FR-4: User Interface
| ID | Requirement | Priority |
|---|---|---|
| FR-4.1 | Mobile-first PWA (installable on iOS/Android) | P0 |
| FR-4.2 | 1-tap floating action button for voice capture | P0 |
| FR-4.3 | Timeline-based note feed (home screen) | P0 |
| FR-4.4 | Bottom navigation: Capture, Library, Insights, Create | P0 |
| FR-4.5 | "Brain View" — AI summaries + connected ideas graph | P1 |
| FR-4.6 | Dark mode by default | P0 |

### FR-5: Music-Specific Features
| ID | Requirement | Priority |
|---|---|---|
| FR-5.1 | Tag audio notes as "Music" category | P0 |
| FR-5.2 | Audio playback with waveform visualization | P1 |
| FR-5.3 | Quick labeling: tempo, mood, genre | P1 |
| FR-5.4 | MIDI/DAW export placeholder | P2 |

### FR-6: Data Management
| ID | Requirement | Priority |
|---|---|---|
| FR-6.1 | Offline capture with background sync | P0 |
| FR-6.2 | Export all data as JSON + media files | P1 |
| FR-6.3 | No vendor lock-in (standard formats) | P1 |

---

## [REQUIREMENTS] 1.3 — Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Voice feedback latency | < 2 seconds from stop-recording to showing clean note |
| NFR-2 | Search response time | < 500ms for semantic search |
| NFR-3 | Offline capability | Full capture + read works offline |
| NFR-4 | Monthly Azure cost | ≤ $150 |
| NFR-5 | PWA Lighthouse score | ≥ 90 (Performance, Accessibility, Best Practices) |
| NFR-6 | API response time (p95) | < 300ms for CRUD operations |
| NFR-7 | Data encryption | At rest (Azure default) + in transit (TLS 1.2+) |
| NFR-8 | Authentication | JWT-based with refresh tokens |

---

## [REQUIREMENTS] 1.4 — User Categories

| Category | Description | Examples |
|---|---|---|
| Music | Musical ideas, melodies, song concepts | Humming, whistling, chord progressions |
| Fitness | Workout logs, body measurements, goals | "Did 5x5 squats at 185 lbs today" |
| Journal | Personal reflections, daily logs | "Feeling grateful for..." |
| Ideas | Random thoughts, project ideas | "What if we built a..." |
| Spiritual | Meditation notes, prayers, insights | "Today's meditation theme was..." |
| Learning | Book notes, course notes, lessons | "Key takeaway from chapter 3..." |

---

## [REQUIREMENTS] 1.5 — Acceptance Criteria for Requirements Phase

- [ ] All functional requirements are testable
- [ ] All non-functional requirements have measurable targets
- [ ] Budget constraint ($150/mo) is acknowledged in architecture choices
- [ ] Phased delivery approach is defined
- [ ] No ambiguous requirements remain

---

# ═══════════════════════════════════════════════════════
# PHASE 2: DESIGN
# ═══════════════════════════════════════════════════════

## [DESIGN] 2.1 — System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    MOBILE DEVICE (PWA)                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────────┐ │
│  │  Capture  │  │ Library  │  │  Insights  │  │   Create   │ │
│  │   Tab     │  │   Tab    │  │    Tab     │  │    Tab     │ │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └─────┬──────┘ │
│       │              │              │               │        │
│  ┌────┴──────────────┴──────────────┴───────────────┴─────┐  │
│  │              Service Worker + IndexedDB                 │  │
│  │         (Offline Cache + Background Sync)               │  │
│  └────────────────────────┬────────────────────────────────┘  │
└───────────────────────────┼──────────────────────────────────┘
                            │ HTTPS
                            ▼
┌───────────────────────────────────────────────────────────────┐
│                 AZURE CONTAINER APPS                           │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                   FastAPI Backend                        │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐  │  │
│  │  │  REST API │  │ WebSocket│  │  Background Workers   │  │  │
│  │  │ Endpoints │  │  (STT)   │  │  (AI Pipeline Queue)  │  │  │
│  │  └────┬─────┘  └────┬─────┘  └──────────┬────────────┘  │  │
│  └───────┼──────────────┼───────────────────┼───────────────┘  │
└──────────┼──────────────┼───────────────────┼─────────────────┘
           │              │                   │
     ┌─────┴─────┐  ┌────┴──────┐  ┌────────┴──────────┐
     │            │  │           │  │                    │
     ▼            ▼  ▼           ▼  ▼                    ▼
┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐
│PostgreSQL│ │  Azure   │ │  Azure   │ │   Azure OpenAI   │
│ Flexible │ │  Blob    │ │ Speech   │ │                  │
│ Server   │ │ Storage  │ │ Service  │ │ • GPT-4o-mini    │
│+pgvector │ │(audio/img)│ │  (STT)  │ │ • text-embedding │
│          │ │          │ │          │ │   -3-small       │
└──────────┘ └──────────┘ └──────────┘ └──────────────────┘
```

---

## [DESIGN] 2.2 — Technology Stack (Final Decisions)

### Frontend
| Component | Technology | Rationale |
|---|---|---|
| Framework | **React 18+ with TypeScript** | Rich ecosystem, PWA support, large community |
| Build Tool | **Vite** | Fast builds, native PWA plugin |
| PWA Plugin | **vite-plugin-pwa (Workbox)** | Service worker generation, offline caching |
| UI Library | **Tailwind CSS + Headless UI** | Mobile-first utility classes, no heavy components |
| State Management | **Zustand** | Lightweight, simple, works with offline sync |
| Local Database | **Dexie.js (IndexedDB wrapper)** | Offline-first data persistence in browser |
| Audio Recording | **MediaRecorder API** | Native browser API, no dependencies |
| Routing | **React Router v6** | Standard SPA routing for PWA |
| Charts/Graphs | **Recharts** (insights) + **react-force-graph** (brain view) | Lightweight visualization |

### Backend
| Component | Technology | Rationale |
|---|---|---|
| Framework | **FastAPI (Python 3.11+)** | Async support, fast, OpenAPI auto-docs |
| Task Queue | **FastAPI BackgroundTasks + asyncio** | Simple async processing, no Redis needed for MVP |
| ORM | **SQLAlchemy 2.0 + asyncpg** | Async PostgreSQL driver, pgvector support |
| Migration | **Alembic** | Database schema migrations |
| Auth | **python-jose (JWT)** | Lightweight JWT auth |
| Audio Processing | **pydub + ffmpeg** | Audio format conversion |
| Containerization | **Docker** | Consistent deployments |

### Azure Services
| Service | SKU/Tier | Est. Monthly Cost |
|---|---|---|
| **Azure Container Apps** | Consumption plan (0.5 vCPU, 1GB) | ~$15-25 |
| **Azure Static Web Apps** | Free tier | $0 |
| **PostgreSQL Flexible Server** | Burstable B1ms (1 vCPU, 2GB) | ~$25-35 |
| **Azure Blob Storage** | Hot tier, LRS | ~$5-10 |
| **Azure Speech Service** | Pay-as-you-go (STT) | ~$10-15 |
| **Azure OpenAI** | GPT-4o-mini + text-embedding-3-small | ~$20-40 |
| **Azure AI Vision** | Pay-as-you-go (OCR) | ~$5 |
| **Total Estimated** | | **~$80-130/month** |

> **Budget buffer**: $20-70/month for scaling or experimentation

---

## [DESIGN] 2.3 — Data Model

### Primary Database: PostgreSQL with pgvector extension

```sql
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- NOTES TABLE (Core Entity)
-- ============================================
CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Content
    content TEXT NOT NULL,                          -- Cleaned/structured text
    raw_transcription TEXT,                         -- Original STT output (before LLM cleanup)
    summary TEXT,                                   -- AI-generated summary

    -- Source
    source_type VARCHAR(20) NOT NULL DEFAULT 'text' -- 'voice', 'text', 'image'
        CHECK (source_type IN ('voice', 'text', 'image')),

    -- Category
    category VARCHAR(30) NOT NULL DEFAULT 'Ideas'
        CHECK (category IN ('Music', 'Fitness', 'Journal', 'Ideas', 'Spiritual', 'Learning')),

    -- Media references (Azure Blob Storage URLs)
    audio_url TEXT,                                 -- Original audio recording
    image_url TEXT,                                 -- Uploaded image
    audio_duration_seconds FLOAT,                   -- Duration of audio clip

    -- AI-extracted metadata
    entities JSONB DEFAULT '[]'::jsonb,             -- Extracted entities [{name, type}]
    mood VARCHAR(30),                               -- AI-detected mood/sentiment
    music_metadata JSONB DEFAULT '{}'::jsonb,       -- {tempo, key, genre, mood} for music notes

    -- Processing state
    processing_status VARCHAR(20) DEFAULT 'raw'
        CHECK (processing_status IN ('raw', 'transcribed', 'processed', 'enriched', 'failed')),

    -- Embeddings for semantic search (1536 dimensions for text-embedding-3-small)
    embedding vector(1536),

    -- Sync
    sync_status VARCHAR(20) DEFAULT 'synced'
        CHECK (sync_status IN ('pending', 'synced', 'conflict')),
    client_id VARCHAR(100),                         -- Client-generated ID for offline sync

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_notes_user_id ON notes(user_id);
CREATE INDEX idx_notes_category ON notes(user_id, category);
CREATE INDEX idx_notes_created_at ON notes(user_id, created_at DESC);
CREATE INDEX idx_notes_processing ON notes(processing_status);
CREATE INDEX idx_notes_sync ON notes(sync_status);
CREATE INDEX idx_notes_source ON notes(source_type);

-- HNSW index for fast vector similarity search
CREATE INDEX idx_notes_embedding ON notes
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================
-- TAGS TABLE
-- ============================================
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    is_auto BOOLEAN DEFAULT FALSE,                  -- TRUE if AI-generated
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- ============================================
-- NOTE-TAGS JUNCTION TABLE
-- ============================================
CREATE TABLE note_tags (
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

-- ============================================
-- NOTE LINKS (Semantic Connections)
-- ============================================
CREATE TABLE note_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    target_note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL,                -- Cosine similarity score
    link_type VARCHAR(30) DEFAULT 'semantic',       -- 'semantic', 'manual', 'temporal'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_note_id, target_note_id)
);

CREATE INDEX idx_note_links_source ON note_links(source_note_id);
CREATE INDEX idx_note_links_target ON note_links(target_note_id);

-- ============================================
-- DAILY SUMMARIES
-- ============================================
CREATE TABLE daily_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    summary_date DATE NOT NULL,
    summary_text TEXT NOT NULL,
    key_themes JSONB DEFAULT '[]'::jsonb,
    note_count INTEGER DEFAULT 0,
    mood_summary VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, summary_date)
);
```

### IndexedDB Schema (Frontend — Dexie.js)

```typescript
// db.ts — Dexie.js local database for offline-first
import Dexie, { Table } from 'dexie';

export interface LocalNote {
  localId: string;          // UUID generated client-side
  serverId?: string;        // UUID from server (after sync)
  content: string;
  rawTranscription?: string;
  sourceType: 'voice' | 'text' | 'image';
  category: string;
  audioBlob?: Blob;         // Raw audio stored locally
  imageBlob?: Blob;         // Raw image stored locally
  tags: string[];
  mood?: string;
  syncStatus: 'pending' | 'synced' | 'conflict';
  processingStatus: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface SyncQueue {
  id?: number;              // Auto-increment
  operation: 'create' | 'update' | 'delete';
  entityType: 'note' | 'tag';
  entityId: string;
  payload: any;
  timestamp: Date;
  retryCount: number;
}

export class CortexDB extends Dexie {
  notes!: Table<LocalNote>;
  syncQueue!: Table<SyncQueue>;

  constructor() {
    super('cortex-db');
    this.version(1).stores({
      notes: 'localId, serverId, sourceType, category, syncStatus, createdAt',
      syncQueue: '++id, operation, entityType, timestamp'
    });
  }
}

export const db = new CortexDB();
```

---

## [DESIGN] 2.4 — API Design

### REST API Endpoints

```yaml
# Authentication
POST   /api/auth/register          # Create account
POST   /api/auth/login              # Get JWT tokens
POST   /api/auth/refresh            # Refresh access token

# Notes CRUD
POST   /api/notes                   # Create note (with optional audio/image upload)
GET    /api/notes                   # List notes (paginated, filterable)
GET    /api/notes/{id}              # Get single note
PUT    /api/notes/{id}              # Update note
DELETE /api/notes/{id}              # Delete note

# Batch Sync (Offline → Online)
POST   /api/sync/push               # Push local changes to server
GET    /api/sync/pull?since={ts}     # Pull server changes since timestamp

# Voice Processing
POST   /api/voice/upload             # Upload audio → transcribe → process → return note
WS     /api/voice/stream             # WebSocket for real-time STT streaming

# AI Operations
POST   /api/ai/process/{note_id}     # Trigger AI pipeline for a note
GET    /api/ai/summary/daily         # Get today's daily summary
GET    /api/ai/summary/weekly        # Get this week's summary
POST   /api/ai/generate              # Express: generate content from notes

# Search
POST   /api/search                   # Semantic + keyword search
GET    /api/search/similar/{note_id} # Find similar notes

# Tags
GET    /api/tags                     # List all tags
POST   /api/tags                     # Create tag

# Insights
GET    /api/insights/patterns        # Get detected patterns
GET    /api/insights/graph           # Get note connection graph data

# Export
GET    /api/export                   # Export all data as JSON + media URLs
```


---

## [DESIGN] 2.5 — AI Pipeline Design (Event-Driven Async)

### Pipeline Architecture

Every note goes through an **asynchronous multi-stage pipeline**. The UI never waits for AI processing to complete.

```
User records voice
       |
       v
+------------------+
| Stage 0: Ingest  |  <- Immediate (< 2s)
| - Upload audio   |
| - STT transcribe |
| - Store raw note |
| - Return to UI   |
+--------+---------+
         | (async background)
         v
+------------------+
| Stage 1: CAPTURE |  <- Background (5-15s)
| - Clean text     |
| - Structure note |
| - Update content |
+--------+---------+
         |
         v
+------------------+
| Stage 2: ORGANIZE|  <- Background (5-15s)
| - Auto-tag       |
| - Categorize     |
| - Gen embeddings |
| - Link notes     |
+--------+---------+
         |
         v
+------------------+
| Stage 3: DISTILL |  <- Scheduled (daily/weekly)
| - Summarize      |
| - Extract themes |
| - Detect patterns|
+------------------+
```

### Pipeline Implementation (FastAPI)

```python
# pipeline/processor.py - AI Processing Pipeline

from enum import Enum
from uuid import UUID
import asyncio, json, logging
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncAzureOpenAI

logger = logging.getLogger(__name__)

class ProcessingStage(str, Enum):
    RAW = 'raw'
    TRANSCRIBED = 'transcribed'
    PROCESSED = 'processed'
    ENRICHED = 'enriched'
    FAILED = 'failed'

class AIPipeline:
    """Event-driven AI processing pipeline for the CODE framework."""

    def __init__(self, openai_client: AsyncAzureOpenAI, db: AsyncSession):
        self.openai = openai_client
        self.db = db

    async def process_note(self, note_id: UUID) -> None:
        """Run the full pipeline. Each stage updates the note in-place."""
        try:
            note = await self._get_note(note_id)
            # Stage 1: CAPTURE - Clean and structure
            if note.processing_status in ('raw', 'transcribed'):
                await self._stage_capture(note)
            # Stage 2: ORGANIZE - Tag, categorize, embed, link
            if note.processing_status == 'processed':
                await self._stage_organize(note)
            logger.info(f'Pipeline complete for note {note_id}')
        except Exception as e:
            logger.error(f'Pipeline failed for note {note_id}: {e}')
            await self._mark_failed(note_id, str(e))

    async def _stage_capture(self, note) -> None:
        """Clean raw transcription into a structured note."""
        prompt = (
            "You are a personal knowledge assistant. Clean and structure this raw voice note.\n"
            "Rules:\n"
            "- Fix grammar and remove filler words (um, uh, like)\n"
            "- Preserve the original meaning and tone\n"
            "- Format into clear paragraphs\n"
            "- If it is a list, format as bullet points\n"
            "- Keep it concise but complete\n\n"
            f"Raw transcription:\n{note.raw_transcription or note.content}\n\n"
            "Return ONLY the cleaned text, nothing else."
        )
        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000, temperature=0.3
        )
        note.content = response.choices[0].message.content
        note.processing_status = ProcessingStage.PROCESSED
        await self.db.commit()

    async def _stage_organize(self, note) -> None:
        """Auto-tag, categorize, generate embeddings, and link related notes."""
        tag_task = asyncio.create_task(self._auto_tag_and_categorize(note))
        embed_task = asyncio.create_task(self._generate_embedding(note))
        await asyncio.gather(tag_task, embed_task)
        await self._link_similar_notes(note)
        note.processing_status = ProcessingStage.ENRICHED
        await self.db.commit()

    async def _auto_tag_and_categorize(self, note) -> None:
        """Use LLM to auto-tag and categorize the note."""
        prompt = (
            "Analyze this note and return a JSON object with:\n"
            "- tags: array of 2-5 relevant tags\n"
            "- category: one of Music, Fitness, Journal, Ideas, Spiritual, Learning\n"
            "- mood: emotional tone\n"
            "- summary: 1-2 sentence summary\n"
            "- entities: array of {name, type}\n\n"
            f"Note content:\n{note.content}\n\nReturn ONLY valid JSON."
        )
        response = await self.openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500, temperature=0.2, response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        note.category = result.get("category", "Ideas")
        note.mood = result.get("mood", "neutral")
        note.summary = result.get("summary", "")
        note.entities = result.get("entities", [])
        for tag_name in result.get("tags", []):
            await self._ensure_tag(note, tag_name, is_auto=True)

    async def _generate_embedding(self, note) -> None:
        """Generate vector embedding for semantic search."""
        response = await self.openai.embeddings.create(
            model="text-embedding-3-small",  # 1536 dimensions
            input=note.content
        )
        note.embedding = response.data[0].embedding

    async def _link_similar_notes(self, note, threshold=0.75, limit=5):
        """Find and link semantically similar notes using pgvector."""
        query = '''
            INSERT INTO note_links (source_note_id, target_note_id, similarity_score, link_type)
            SELECT :note_id, n.id,
                   1 - (n.embedding <=> :embedding) AS score,
                   'semantic'
            FROM notes n
            WHERE n.id != :note_id AND n.user_id = :user_id
              AND n.embedding IS NOT NULL
              AND 1 - (n.embedding <=> :embedding) > :threshold
            ORDER BY n.embedding <=> :embedding LIMIT :limit
            ON CONFLICT (source_note_id, target_note_id)
            DO UPDATE SET similarity_score = EXCLUDED.similarity_score;
        '''
        await self.db.execute(query, {
            "note_id": note.id, "embedding": note.embedding,
            "user_id": note.user_id, "threshold": threshold, "limit": limit
        })
```

### Daily/Weekly Distill Pipeline (Scheduled)

```python
# pipeline/distill.py - Scheduled summarization

async def generate_daily_summary(user_id: UUID, target_date: date) -> None:
    """Generate daily summary from all notes created on target_date."""
    notes = await get_notes_for_date(user_id, target_date)
    if not notes:
        return
    notes_text = "\n---\n".join([f"[{n.category}] {n.content}" for n in notes])
    prompt = (
        "You are a personal thinking assistant. Summarize this persons day based on their notes.\n"
        "Include: Key themes, emotional tone, notable ideas, connections between notes.\n"
        f"Notes from today:\n{notes_text}\n\n"
        "Write a warm, insightful 3-5 paragraph summary. Speak directly to the person."
    )
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800, temperature=0.7
    )
    await save_daily_summary(user_id, target_date, response.choices[0].message.content)
```

---

## [DESIGN] 2.6 — Voice-First UX Architecture

### Critical Requirement: < 2 Second Feedback Loop

```
  VOICE CAPTURE FLOW

  [1] User taps FAB          -> Recording starts
  [2] User taps again         -> Recording stops
  [3] Audio sent to backend   -> Immediate 'Processing...' UI
  [4] STT result returns      -> Show raw text (< 2s)
  [5] Background pipeline     -> Note updates silently
  [6] User sees final note    -> Clean text + tags + category
```

### Implementation: Real-Time STT via WebSocket

```python
# api/voice.py - WebSocket endpoint for real-time STT

from fastapi import WebSocket, WebSocketDisconnect
import azure.cognitiveservices.speech as speechsdk

@router.websocket("/api/voice/stream")
async def voice_stream(websocket: WebSocket):
    """Stream audio from client -> Azure STT -> send text back in real-time."""
    await websocket.accept()
    speech_config = speechsdk.SpeechConfig(
        subscription=settings.AZURE_SPEECH_KEY,
        region=settings.AZURE_SPEECH_REGION
    )
    speech_config.speech_recognition_language = "en-US"
    push_stream = speechsdk.audio.PushAudioInputStream()
    audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    async def on_recognized(evt):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            await websocket.send_json({"type": "transcription", "text": evt.result.text, "is_final": True})

    async def on_recognizing(evt):
        await websocket.send_json({"type": "partial", "text": evt.result.text, "is_final": False})

    recognizer.recognized.connect(on_recognized)
    recognizer.recognizing.connect(on_recognizing)
    recognizer.start_continuous_recognition()
    try:
        while True:
            data = await websocket.receive_bytes()
            push_stream.write(data)
    except WebSocketDisconnect:
        push_stream.close()
        recognizer.stop_continuous_recognition()
```

### Frontend: Voice Capture Component

```typescript
// components/VoiceCapture.tsx
import { useState, useRef } from 'react';
import { db, LocalNote } from '../db';
import { v4 as uuidv4 } from 'uuid';

export function VoiceCapture() {
  const [isRecording, setIsRecording] = useState(false);
  const [partialText, setPartialText] = useState('');
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    mediaRecorderRef.current = mediaRecorder;
    chunksRef.current = [];
    // Open WebSocket for real-time STT
    const ws = new WebSocket(`${WS_BASE_URL}/api/voice/stream`);
    wsRef.current = ws;
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setPartialText(data.text);
    };
    mediaRecorder.ondataavailable = (event) => {
      chunksRef.current.push(event.data);
      if (ws.readyState === WebSocket.OPEN) {
        event.data.arrayBuffer().then(buf => ws.send(buf));
      }
    };
    mediaRecorder.start(250); // Send chunks every 250ms
    setIsRecording(true);
  };

  const stopRecording = async () => {
    mediaRecorderRef.current?.stop();
    wsRef.current?.close();
    setIsRecording(false);
    const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
    // Save locally FIRST (offline-first)
    const localNote: LocalNote = {
      localId: uuidv4(),
      content: partialText || '(Transcribing...)',
      rawTranscription: partialText,
      sourceType: 'voice',
      category: 'Ideas',
      audioBlob,
      tags: [],
      syncStatus: 'pending',
      processingStatus: 'raw',
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    await db.notes.add(localNote);
    await db.syncQueue.add({
      operation: 'create', entityType: 'note',
      entityId: localNote.localId, payload: localNote,
      timestamp: new Date(), retryCount: 0,
    });
    if (navigator.onLine) { syncManager.pushChanges(); }
    setPartialText('');
  };

  return (
    <button
      onClick={isRecording ? stopRecording : startRecording}
      className={`fixed bottom-20 right-6 w-16 h-16 rounded-full shadow-2xl
        flex items-center justify-center z-50 transition-all duration-200
        ${isRecording ? 'bg-red-500 animate-pulse scale-110' : 'bg-indigo-600 hover:bg-indigo-700'}`}
    >
      {isRecording ? <MicOffIcon /> : <MicIcon />}
    </button>
  );
}
```

---

## [DESIGN] 2.7 — Offline-First Architecture

### Strategy: Local-First with Background Sync

```
                    DATA FLOW

  User Action -> Write to IndexedDB -> Update UI
                        |
                        v
                Add to Sync Queue
                        |
                        v
                +---------------+
                | Online?       |
                |  Yes -> Push  |
                |  No  -> Wait  |
                +---------------+
                        |
                (When online)
                        v
                Process Sync Queue (FIFO)
                - POST /api/sync/push
                - Handle conflicts
                - Update local syncStatus
```

### Service Worker Configuration (Workbox via vite-plugin-pwa)

```typescript
// vite.config.ts - PWA configuration
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'Cortex - Second Brain',
        short_name: 'Cortex',
        description: 'AI-powered personal knowledge system',
        theme_color: '#4F46E5',
        background_color: '#0F172A',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512-mask.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
        ]
      },
      workbox: {
        runtimeCaching: [
          {
            urlPattern: /^\/api\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 200, maxAgeSeconds: 86400 },
              networkTimeoutSeconds: 3,
            }
          },
          {
            urlPattern: /\.blob\.core\.windows\.net/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'media-cache',
              expiration: { maxEntries: 100, maxAgeSeconds: 604800 }
            }
          }
        ]
      }
    })
  ]
});
```

### Sync Engine Implementation

```typescript
// sync/syncManager.ts - Offline sync engine
import { db } from '../db';

class SyncManager {
  private isSyncing = false;

  constructor() {
    window.addEventListener('online', () => this.pushChanges());
    setInterval(() => {
      if (navigator.onLine && !this.isSyncing) this.pushChanges();
    }, 30000);
  }

  async pushChanges(): Promise<void> {
    if (this.isSyncing || !navigator.onLine) return;
    this.isSyncing = true;
    try {
      const queue = await db.syncQueue.orderBy('timestamp').toArray();
      for (const item of queue) {
        try {
          if (item.operation === 'create' && item.entityType === 'note') {
            const note = await db.notes.get(item.entityId);
            if (!note) continue;
            let audioUrl: string | undefined;
            if (note.audioBlob) {
              audioUrl = await this.uploadBlob(note.audioBlob, `audio/${note.localId}.webm`);
            }
            const response = await fetch('/api/notes', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${getAccessToken()}` },
              body: JSON.stringify({
                client_id: note.localId, content: note.content,
                source_type: note.sourceType, audio_url: audioUrl, category: note.category, tags: note.tags
              })
            });
            if (response.ok) {
              const serverNote = await response.json();
              await db.notes.update(note.localId, { serverId: serverNote.id, syncStatus: 'synced' });
              await db.syncQueue.delete(item.id!);
            }
          }
        } catch (err) {
          await db.syncQueue.update(item.id!, { retryCount: item.retryCount + 1 });
          if (item.retryCount >= 5) await db.syncQueue.delete(item.id!);
        }
      }
    } finally { this.isSyncing = false; }
  }

  private async uploadBlob(blob: Blob, path: string): Promise<string> {
    const formData = new FormData();
    formData.append('file', blob, path);
    const res = await fetch('/api/upload', {
      method: 'POST', headers: { 'Authorization': `Bearer ${getAccessToken()}` }, body: formData
    });
    return (await res.json()).url;
  }
}
export const syncManager = new SyncManager();
```

---

## [DESIGN] 2.8 — Semantic Search Implementation

### Search Endpoint (FastAPI + pgvector)

```python
# api/search.py - Semantic + hybrid search
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()

class SearchRequest(BaseModel):
    query: str
    category: str | None = None
    tags: list[str] | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 20

@router.post('/api/search')
async def semantic_search(request: SearchRequest, user_id: UUID = Depends(get_current_user)):
    # Generate query embedding
    embed_response = await openai.embeddings.create(
        model="text-embedding-3-small", input=request.query
    )
    query_embedding = embed_response.data[0].embedding

    # Hybrid search: semantic (70%) + full-text (30%)
    query = '''
        SELECT n.id, n.content, n.summary, n.category, n.created_at,
               1 - (n.embedding <=> :query_embedding::vector) AS semantic_score,
               ts_rank(to_tsvector('english', n.content),
                       plainto_tsquery('english', :query_text)) AS text_score,
               (0.7 * (1 - (n.embedding <=> :query_embedding::vector))) +
               (0.3 * COALESCE(ts_rank(to_tsvector('english', n.content),
                       plainto_tsquery('english', :query_text)), 0)) AS combined_score
        FROM notes n
        WHERE n.user_id = :user_id AND n.embedding IS NOT NULL
    '''
    params = {'query_embedding': query_embedding, 'query_text': request.query, 'user_id': str(user_id)}
    if request.category:
        query += ' AND n.category = :category'
        params['category'] = request.category
    if request.date_from:
        query += ' AND n.created_at >= :date_from'
        params['date_from'] = request.date_from
    if request.date_to:
        query += ' AND n.created_at <= :date_to'
        params['date_to'] = request.date_to
    query += ' ORDER BY combined_score DESC LIMIT :limit'
    params['limit'] = request.limit
    results = await db.execute(text(query), params)
    return [dict(row._mapping) for row in results]
```

---

## [DESIGN] 2.9 — Music-Specific Features

### Music Note Processing

```python
# pipeline/music.py - Music-specific AI processing

async def process_music_note(note) -> None:
    """Extract music-specific metadata from a music note."""
    prompt = (
        "Analyze this music-related note and return JSON with:\n"
        "- tempo_guess: estimated BPM if mentioned (null if unknown)\n"
        "- key_guess: musical key if mentioned (null if unknown)\n"
        "- genre: likely genre\n"
        "- mood: musical mood\n"
        "- instruments: array of instruments mentioned\n"
        "- description: 1-sentence description of the musical idea\n"
        "- development_suggestions: 2-3 suggestions for developing this idea\n\n"
        f"Note content: {note.content}\n\nReturn ONLY valid JSON."
    )
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    note.music_metadata = json.loads(response.choices[0].message.content)
    await db.commit()
```

### Frontend: Music Playback with Waveform (use wavesurfer.js)

Display audio waveform, playback controls, and music metadata chips (BPM, key, genre, mood).
Use dark theme colors: waveColor '#6366F1', progressColor '#4F46E5'.

---

## [DESIGN] 2.10 — Security Design

### Authentication Flow (JWT)

```
  Client (PWA)                Backend (FastAPI)
      |                              |
      | POST /api/auth/login         |
      | {email, password}            |
      |----------------------------->|
      |                              | Verify credentials
      |                              | Generate JWT pair
      | {access_token,               |
      |  refresh_token}              |
      |<-----------------------------|
      |                              |
      | Store access_token in memory |
      | Store refresh in httpOnly    |
      | cookie (secure, sameSite)    |
      |                              |
      | GET /api/notes               |
      | Authorization: Bearer {at}   |
      |----------------------------->|  Validate JWT
      | 200 OK {notes}               |
      |<-----------------------------|
```

### Auth Implementation

```python
# auth/jwt.py - JWT authentication
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer

SECRET_KEY = settings.JWT_SECRET_KEY  # From Azure Key Vault
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "access"}, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "exp": expire, "type": "refresh"}, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials=Depends(security)) -> UUID:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return UUID(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```

---

## [DESIGN] 2.11 — Cost Budget Breakdown ($150/month)

### Azure Service Costs (Estimated)

| Service | SKU / Tier | What For | Est. Cost/mo |
|---|---|---|---|
| **Azure Static Web Apps** | Free tier | Host PWA frontend | $0 |
| **Azure Container Apps** | Consumption (0.5 vCPU, 1GB) | FastAPI backend | $15-25 |
| **PostgreSQL Flexible Server** | Burstable B1ms (1 vCPU, 2GB RAM, 32GB storage) | Notes DB + pgvector | $25-35 |
| **Azure Blob Storage** | Hot tier, LRS, ~10GB | Audio files, images | $5-10 |
| **Azure Speech Service** | Pay-as-you-go (~5 hrs/mo STT) | Voice transcription | $10-15 |
| **Azure OpenAI** | GPT-4o-mini (~500K tokens/mo) + text-embedding-3-small (~1M tokens/mo) | AI pipeline | $15-30 |
| **Azure AI Vision** | Pay-as-you-go (~100 images/mo OCR) | Image OCR | $2-5 |
| **Azure Container Registry** | Basic tier | Docker images | $5 |
| **TOTAL** | | | **$77-$145** |

### Cost Optimization Strategies

1. **Use GPT-4o-mini everywhere** — it is 15x cheaper than GPT-4o and sufficient for tagging, summarization, and structuring
2. **Use text-embedding-3-small** — 5x cheaper than text-embedding-3-large, 1536 dimensions is sufficient for personal notes
3. **Batch embedding generation** — process multiple notes in one API call
4. **Cache daily summaries** — do not regenerate unless new notes are added
5. **Scale Container Apps to zero** — consumption plan charges only when active
6. **PostgreSQL auto-stop** — configure auto-pause during inactive hours (saves ~30%)
7. **Use Azure Free Tier** for Static Web Apps (no cost for frontend hosting)
8. **Set Azure budget alerts** at $100 and $140 to avoid overruns

### Token Budget Per Note (Estimated)

| Operation | Model | Input Tokens | Output Tokens | Cost per Note |
|---|---|---|---|---|
| Clean transcription | GPT-4o-mini | ~300 | ~200 | $0.0001 |
| Auto-tag + categorize | GPT-4o-mini | ~400 | ~150 | $0.0001 |
| Generate embedding | text-embedding-3-small | ~200 | — | $0.000004 |
| **Total per note** | | | | **~$0.0002** |
| **Monthly (1000 notes)** | | | | **~$0.20** |

> The AI cost per note is negligible. The main costs are infrastructure (PostgreSQL + Container Apps).

---

## [DESIGN] 2.12 — Design Phase Acceptance Criteria

- [ ] Architecture diagram matches implementation plan
- [ ] All API endpoints are defined with request/response schemas
- [ ] Data model supports all functional requirements
- [ ] Offline-first sync strategy is clearly defined
- [ ] Voice pipeline achieves < 2s feedback target
- [ ] Total estimated Azure cost is within $150/month budget
- [ ] Security model (JWT) is complete
- [ ] PWA manifest is properly configured for mobile installation

---

# ===============================================
# PHASE 3: CRITIQUE
# ===============================================

## [CRITIQUE] 3.1 — Architecture Validation Questions

The Critique agent MUST evaluate the design against these questions:

### Scalability
- Can the PostgreSQL B1ms tier handle 10,000+ notes with pgvector HNSW index?
- Will Container Apps consumption plan handle burst traffic (e.g., rapid voice captures)?
- Is the sync queue design robust enough for 100+ pending items?

### Reliability
- What happens if the AI pipeline fails mid-processing? Is there retry logic?
- What happens if Azure OpenAI rate limits are hit? Is there backoff?
- Is data safe if the user closes the app during voice recording?
- What if sync fails repeatedly? Is there a dead-letter mechanism?

### Cost
- Are there any hidden costs (egress, transactions, etc.)?
- Could the embedding generation cost spike with large notes?
- Is Container Apps consumption plan truly scale-to-zero?

### Security
- Is the JWT secret stored securely (not in code)?
- Are Blob Storage URLs signed (SAS tokens) or public?
- Is the WebSocket endpoint authenticated?

### UX
- Does the offline-first approach create confusion when AI processing is delayed?
- Is there clear visual feedback for sync status?
- Can the user manually correct AI-generated tags and categories?

## [CRITIQUE] 3.2 — Required Mitigations

The following MUST be implemented based on critique:

1. **Retry with exponential backoff** for all Azure API calls (Speech, OpenAI, Blob)
2. **Dead-letter queue** for sync items that fail 5+ times (store in IndexedDB separate table)
3. **SAS tokens** for Blob Storage URLs (time-limited, read-only)
4. **WebSocket authentication** via query parameter token (validated on connect)
5. **Processing status indicator** in UI showing: raw -> transcribed -> processed -> enriched
6. **Manual override UI** for category, tags, and mood on any note
7. **Graceful degradation** if AI services are down (notes still save, just without AI enrichment)
8. **Rate limiting** on the backend API (100 requests/minute per user)

## [CRITIQUE] 3.3 — Critique Phase Acceptance Criteria

- [ ] All critique questions have been addressed
- [ ] Retry and error handling patterns are defined
- [ ] Security gaps have mitigations
- [ ] No single point of failure exists that loses user data
- [ ] Cost estimation accounts for edge cases

---

# ===============================================
# PHASE 4: CODING
# ===============================================

## [CODING] 4.1 — Repository Structure

```
cortex/
├── README.md
├── .github/
│   └── workflows/
│       ├── deploy-frontend.yml
│       └── deploy-backend.yml
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   ├── public/
│   │   ├── manifest.json
│   │   ├── favicon.ico
│   │   └── icons/
│   │       ├── icon-192.png
│   │       ├── icon-512.png
│   │       └── icon-512-mask.png
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── db.ts                    # Dexie.js IndexedDB schema
│       ├── api/
│       │   ├── client.ts             # Axios/fetch wrapper with auth
│       │   ├── notes.ts              # Notes API calls
│       │   ├── search.ts             # Search API calls
│       │   └── auth.ts               # Auth API calls
│       ├── components/
│       │   ├── VoiceCapture.tsx       # FAB + recording logic
│       │   ├── NoteCard.tsx           # Note display card
│       │   ├── NoteEditor.tsx         # Edit note (tags, category)
│       │   ├── SearchBar.tsx          # Semantic search input
│       │   ├── MusicPlayer.tsx        # Waveform audio player
│       │   ├── BottomNav.tsx          # Bottom navigation tabs
│       │   ├── ProcessingBadge.tsx    # Status indicator
│       │   └── SyncIndicator.tsx      # Online/offline + sync status
│       ├── pages/
│       │   ├── CapturePage.tsx        # Voice/text/image capture
│       │   ├── LibraryPage.tsx        # Browse all notes
│       │   ├── InsightsPage.tsx       # Daily summaries, patterns
│       │   ├── CreatePage.tsx         # AI-generated content
│       │   ├── NoteDetailPage.tsx     # Single note view
│       │   ├── SearchPage.tsx         # Search results
│       │   ├── LoginPage.tsx          # Authentication
│       │   └── BrainViewPage.tsx      # Knowledge graph visualization
│       ├── hooks/
│       │   ├── useAuth.ts
│       │   ├── useNotes.ts
│       │   ├── useVoiceRecorder.ts
│       │   └── useSync.ts
│       ├── store/
│       │   ├── authStore.ts           # Zustand auth state
│       │   ├── noteStore.ts           # Zustand note state
│       │   └── uiStore.ts             # UI state (loading, modals)
│       ├── sync/
│       │   └── syncManager.ts         # Offline sync engine
│       ├── styles/
│       │   └── globals.css
│       └── utils/
│           ├── audio.ts               # Audio recording helpers
│           └── formatters.ts          # Date, text formatters
├── backend/
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │       └── 001_initial_schema.py
│   └── app/
│       ├── main.py                   # FastAPI app entry point
│       ├── config.py                 # Settings from env vars
│       ├── database.py               # Async SQLAlchemy engine
│       ├── models/
│       │   ├── __init__.py
│       │   ├── user.py
│       │   ├── note.py
│       │   ├── tag.py
│       │   └── daily_summary.py
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── note.py               # Pydantic request/response
│       │   ├── search.py
│       │   ├── auth.py
│       │   └── sync.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── notes.py              # CRUD endpoints
│       │   ├── search.py             # Search endpoints
│       │   ├── voice.py              # Voice upload + WebSocket STT
│       │   ├── sync.py               # Sync push/pull endpoints
│       │   ├── insights.py           # Summary + pattern endpoints
│       │   ├── export.py             # Data export endpoint
│       │   └── auth.py               # Login, register, refresh
│       ├── auth/
│       │   └── jwt.py                # JWT creation + validation
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── processor.py          # Main AI pipeline
│       │   ├── distill.py            # Daily/weekly summaries
│       │   ├── music.py              # Music-specific processing
│       │   └── ocr.py                # Image OCR via Azure Vision
│       ├── services/
│       │   ├── blob_storage.py       # Azure Blob operations
│       │   ├── speech.py             # Azure Speech STT
│       │   └── openai_client.py      # Azure OpenAI client setup
│       └── utils/
│           ├── audio.py              # Audio format conversion
│           └── retry.py              # Exponential backoff helper
├── infra/
│   ├── main.bicep                    # Azure Bicep IaC template
│   ├── modules/
│   │   ├── container-app.bicep
│   │   ├── postgres.bicep
│   │   ├── storage.bicep
│   │   ├── cognitive-services.bicep
│   │   └── static-web-app.bicep
│   ├── deploy.sh                     # One-click deploy script
│   └── parameters.json
└── docs/
    ├── ARCHITECTURE.md
    ├── API_REFERENCE.md
    ├── DEPLOYMENT.md
    └── EXTENDING.md
```

## [CODING] 4.2 — Phased MVP Implementation Plan

### PHASE 1 (MVP) — Capture + Store + Search
**Target: 2-3 weeks | This is the FIRST thing to build**

Build order (STRICTLY follow this sequence):

```
Week 1: Foundation
  1. Set up monorepo structure (frontend/ + backend/ + infra/)
  2. Backend: FastAPI skeleton with health check endpoint
  3. Backend: PostgreSQL models + Alembic migrations (users, notes, tags)
  4. Backend: JWT auth (register, login, refresh, protect routes)
  5. Backend: Notes CRUD API (create, read, update, delete, list with pagination)
  6. Backend: Dockerfile + test locally

Week 2: Voice + AI + Frontend
  7. Backend: Azure Blob Storage integration (upload audio/images)
  8. Backend: Azure Speech STT integration (file upload mode first)
  9. Backend: AI pipeline Stage 1 (Capture: clean transcription)
  10. Backend: AI pipeline Stage 2 (Organize: auto-tag, categorize, embedding)
  11. Backend: Semantic search endpoint with pgvector
  12. Frontend: Vite + React + Tailwind + PWA setup
  13. Frontend: Auth pages (login, register)
  14. Frontend: IndexedDB (Dexie.js) local database setup

Week 3: Voice UX + Offline + Deploy
  15. Frontend: Voice capture FAB component (MediaRecorder API)
  16. Frontend: Note feed (timeline view) with category filters
  17. Frontend: Search page with semantic search
  18. Frontend: Offline sync engine (queue + push/pull)
  19. Frontend: Bottom navigation (Capture, Library, Search)
  20. Infra: Bicep templates + deploy.sh
  21. Deploy to Azure + test on mobile browser
```

### PHASE 2 — Insights + Brain View
**Target: 2 weeks**

```
  22. Backend: Daily/weekly summary generation (distill pipeline)
  23. Backend: Scheduled task for auto-generating summaries
  24. Backend: Note links API (graph data)
  25. Backend: Pattern detection endpoint
  26. Frontend: Insights page (daily/weekly summaries)
  27. Frontend: Brain View page (force-directed graph of connected notes)
  28. Frontend: Processing status badges on note cards
  29. Backend: WebSocket real-time STT streaming
  30. Frontend: Real-time transcription feedback during recording
```

### PHASE 3 — Music + Express + Polish
**Target: 2 weeks**

```
  31. Backend: Music-specific AI processing pipeline
  32. Frontend: Music player with waveform (wavesurfer.js)
  33. Frontend: Music metadata display (tempo, key, genre, mood)
  34. Backend: Express endpoints (generate song ideas, practice plans, reflections)
  35. Frontend: Create page (express features)
  36. Backend: Data export endpoint (JSON + media URLs)
  37. Frontend: Settings page (export data, change password)
  38. Backend: Image upload + OCR via Azure AI Vision
  39. Frontend: Image capture/upload in Capture page
  40. End-to-end testing + performance optimization
```

## [CODING] 4.3 — Key Dependencies

### Frontend (package.json)

```json
{
  "name": "cortex-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "zustand": "^4.5.0",
    "dexie": "^4.0.0",
    "dexie-react-hooks": "^1.1.0",
    "uuid": "^10.0.0",
    "recharts": "^2.12.0",
    "react-force-graph-2d": "^1.25.0",
    "wavesurfer.js": "^7.8.0",
    "lucide-react": "^0.400.0",
    "date-fns": "^3.6.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@types/uuid": "^10.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vite-plugin-pwa": "^0.20.0",
    "vitest": "^2.0.0"
  }
}
```

### Backend (requirements.txt)

```
fastapi==0.115.*
uvicorn[standard]==0.30.*
sqlalchemy[asyncio]==2.0.*
asyncpg==0.29.*
pgvector==0.3.*
alembic==1.13.*
python-jose[cryptography]==3.3.*
passlib[bcrypt]==1.7.*
python-multipart==0.0.*
openai==1.40.*
azure-cognitiveservices-speech==1.40.*
azure-storage-blob==12.22.*
azure-ai-vision-imageanalysis==1.0.*
pydub==0.25.*
httpx==0.27.*
pydantic-settings==2.4.*
tenacity==8.5.*    # Retry with backoff
```

### Backend Dockerfile

```dockerfile
FROM python:3.11-slim

# Install ffmpeg for audio processing
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
COPY alembic.ini .
COPY alembic/ ./alembic/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## [CODING] 4.4 — Environment Variables

```bash
# .env (NEVER commit this file)

# Database
DATABASE_URL=postgresql+asyncpg://cortexadmin:<password>@cortex-db.postgres.database.azure.com:5432/cortex

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://cortex-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_API_VERSION=2024-10-21

# Azure Speech
AZURE_SPEECH_KEY=<your-key>
AZURE_SPEECH_REGION=westus2

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING=<your-connection-string>
AZURE_STORAGE_CONTAINER=cortex-media

# Azure AI Vision
AZURE_VISION_ENDPOINT=https://cortex-vision.cognitiveservices.azure.com/
AZURE_VISION_KEY=<your-key>

# JWT
JWT_SECRET_KEY=<generate-a-secure-random-string-64-chars>

# App
CORS_ORIGINS=https://cortex-app.azurestaticapps.net,http://localhost:5173
ENVIRONMENT=production
```

## [CODING] 4.5 — Coding Phase Acceptance Criteria

- [ ] All Phase 1 features implemented and working locally
- [ ] PWA installable on both iOS Safari and Android Chrome
- [ ] Voice capture records, transcribes, and stores notes
- [ ] Semantic search returns relevant results
- [ ] Offline capture works (create note without internet, syncs when online)
- [ ] JWT auth protects all API endpoints
- [ ] Docker container builds and runs successfully
- [ ] All database migrations run cleanly
- [ ] No TypeScript or Python type errors
- [ ] API auto-docs available at /docs (Swagger UI)

---

# ===============================================
# PHASE 5: REVIEW
# ===============================================

## [REVIEW] 5.1 — Testing Strategy

### Backend Tests (pytest)

```python
# tests/test_notes.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_note(client: AsyncClient, auth_headers: dict):
    response = await client.post('/api/notes', json={
        'content': 'Test note content',
        'source_type': 'text',
        'category': 'Ideas'
    }, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data['content'] == 'Test note content'
    assert data['processing_status'] == 'raw'

@pytest.mark.asyncio
async def test_semantic_search(client: AsyncClient, auth_headers: dict, seeded_notes):
    response = await client.post('/api/search', json={
        'query': 'workout routine',
        'limit': 5
    }, headers=auth_headers)
    assert response.status_code == 200
    results = response.json()
    assert len(results) > 0
    # Fitness note should rank higher than unrelated notes
    assert results[0]['category'] == 'Fitness'

@pytest.mark.asyncio
async def test_offline_sync(client: AsyncClient, auth_headers: dict):
    # Simulate pushing a batch of offline-created notes
    response = await client.post('/api/sync/push', json={
        'operations': [
            {'operation': 'create', 'entity_type': 'note', 'client_id': 'local-uuid-1',
             'payload': {'content': 'Offline note 1', 'source_type': 'text', 'category': 'Journal'}},
            {'operation': 'create', 'entity_type': 'note', 'client_id': 'local-uuid-2',
             'payload': {'content': 'Offline note 2', 'source_type': 'voice', 'category': 'Music'}}
        ]
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data['synced_count'] == 2
```

### Frontend Tests (Vitest)

```typescript
// __tests__/syncManager.test.ts
import { describe, it, expect, vi } from 'vitest';
import { db } from '../src/db';

describe('SyncManager', () => {
  it('should queue operations when offline', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    await db.notes.add({
      localId: 'test-uuid', content: 'Test note',
      sourceType: 'text', category: 'Ideas', tags: [],
      syncStatus: 'pending', processingStatus: 'raw',
      createdAt: new Date(), updatedAt: new Date()
    });
    const pendingNotes = await db.notes.where('syncStatus').equals('pending').toArray();
    expect(pendingNotes).toHaveLength(1);
  });
});
```

## [REVIEW] 5.2 — Deployment (Azure)

### One-Click Deploy Script

```bash
#!/bin/bash
# infra/deploy.sh - Deploy Cortex to Azure
set -e

# Variables
RESOURCE_GROUP="cortex-rg"
LOCATION="westus2"
APP_NAME="cortex"

echo '=== Step 1: Create Resource Group ==='
az group create --name $RESOURCE_GROUP --location $LOCATION

echo '=== Step 2: Deploy Infrastructure (Bicep) ==='
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file infra/main.bicep \
  --parameters infra/parameters.json \
  --parameters appName=$APP_NAME

echo '=== Step 3: Build and Push Backend Container ==='
ACR_NAME=$(az acr list --resource-group $RESOURCE_GROUP --query '[0].name' -o tsv)
az acr build --registry $ACR_NAME --image cortex-api:latest ./backend

echo '=== Step 4: Deploy Backend to Container Apps ==='
az containerapp update \
  --name ${APP_NAME}-api \
  --resource-group $RESOURCE_GROUP \
  --image ${ACR_NAME}.azurecr.io/cortex-api:latest

echo '=== Step 5: Run Database Migrations ==='
az containerapp exec \
  --name ${APP_NAME}-api \
  --resource-group $RESOURCE_GROUP \
  --command "alembic upgrade head"

echo '=== Step 6: Build and Deploy Frontend ==='
cd frontend
npm run build
cd ..
az staticwebapp create \
  --name ${APP_NAME}-app \
  --resource-group $RESOURCE_GROUP \
  --source ./frontend \
  --location $LOCATION \
  --output-location dist

echo "=== Deployment Complete! ==="
echo "Frontend: https://${APP_NAME}-app.azurestaticapps.net"
echo "Backend:  https://${APP_NAME}-api.<region>.azurecontainerapps.io"
```

### Bicep IaC Template (infra/main.bicep)

```bicep
// infra/main.bicep - Main Azure infrastructure template
targetScope = 'resourceGroup'

@description('Base name for all resources')
param appName string = 'cortex'

@description('Azure region')
param location string = resourceGroup().location

@secure()
@description('PostgreSQL admin password')
param dbAdminPassword string

@secure()
@description('JWT secret key')
param jwtSecretKey string

// PostgreSQL Flexible Server
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: '${appName}-db'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: 'cortexadmin'
    administratorLoginPassword: dbAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
  }
}

// Enable pgvector extension
resource pgvectorExt 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'azure.extensions'
  properties: { value: 'VECTOR,UUID-OSSP', source: 'user-override' }
}

// Storage Account
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${appName}storage'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
}

// Azure OpenAI
resource openai 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-openai'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// Azure Speech
resource speech 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: '${appName}-speech'
  location: location
  kind: 'SpeechServices'
  sku: { name: 'S0' }
  properties: { publicNetworkAccess: 'Enabled' }
}

// Container App Environment
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
  location: location
  properties: {}
}

// Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: '${appName}acr'
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

// Output connection strings (for setting env vars)
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output storageAccountName string = storage.name
output openaiEndpoint string = openai.properties.endpoint
output speechRegion string = location
output acrLoginServer string = acr.properties.loginServer
```

## [REVIEW] 5.3 — Review Phase Acceptance Criteria (Final Checklist)

### Functional
- [ ] Voice capture: 1-tap record, transcribe, store (< 2s feedback)
- [ ] Text input: create and edit text notes
- [ ] Auto-tagging: notes get 2-5 relevant tags automatically
- [ ] Auto-categorization: notes classified into correct category
- [ ] Semantic search: natural language queries return relevant results
- [ ] Offline capture: notes saved locally when offline, sync when online
- [ ] Timeline feed: notes displayed chronologically with filters
- [ ] Authentication: register, login, protected routes

### Non-Functional
- [ ] PWA installable on iOS and Android
- [ ] Lighthouse PWA score >= 90
- [ ] API response time < 300ms (p95)
- [ ] Voice feedback < 2 seconds
- [ ] Azure monthly cost within $150 budget

### Code Quality
- [ ] TypeScript strict mode, no any types
- [ ] Python type hints on all functions
- [ ] API endpoints documented (FastAPI auto-docs)
- [ ] Error handling on all external API calls (retry + fallback)
- [ ] No secrets in source code
- [ ] Clean git history with meaningful commit messages

### Deployment
- [ ] Bicep template deploys all Azure resources
- [ ] deploy.sh runs end-to-end without manual steps
- [ ] Database migrations run automatically
- [ ] Frontend accessible via Azure Static Web Apps URL
- [ ] Backend API accessible via Container Apps URL
- [ ] CORS configured correctly between frontend and backend

---

# ===============================================
# APPENDIX
# ===============================================

## A.1 — Design Philosophy (Remind Yourself)

1. **Frictionless capture > everything** — The fastest path from thought to stored note wins
2. **AI augments thinking, does not replace it** — AI suggests, user decides
3. **System feels like memory, not a database** — Warm, personal, intelligent
4. **Offline is not an edge case** — It is the default state
5. **Cost-conscious by design** — Use the cheapest model that works, scale later

## A.2 — Key Research References

- **Azure Speech STT**: Supports real-time streaming, batch, and fast transcription modes. Use streaming for live UX, batch for accuracy re-processing. Embedded speech available for offline fallback.
- **Offline-First Architecture**: Local-first with queue-based sync is the proven pattern. Use IndexedDB (Dexie.js) as local store, sync via FIFO queue with retry and conflict detection.
- **Vector Search (pgvector)**: PostgreSQL with pgvector is the simplest and most cost-effective option for personal-scale apps (< 100K vectors). HNSW index with cosine distance recommended. Upgrade to Azure AI Search only if hybrid ranking becomes critical.
- **Voice Latency**: Key strategies — stream audio in chunks (not full recording upload), keep speech service in same Azure region as backend, use real-time streaming mode, provide partial transcription results to UI immediately.
- **Cost Control**: GPT-4o-mini is 15x cheaper than GPT-4o. text-embedding-3-small is 5x cheaper than large. Container Apps consumption plan scales to zero. PostgreSQL B1ms with auto-pause saves ~30%.
- **PWA as Mobile App**: Progressive Web App with standalone display mode is installable on both iOS and Android without app store submission. Service worker enables offline caching. This is significantly cheaper than React Native for a personal-use app.

## A.3 — Quick Start for Claude Code Agent Teams

```
To start building, feed this spec to Claude Code Agent Teams and say:

  "Build the Cortex Second Brain app following this spec.
   Start with Phase 1 MVP (items 1-21 in section 4.2).
   Use the exact folder structure in section 4.1.
   Use the exact dependencies in section 4.3.
   Follow the architecture in section 2.1.
   Deploy to Azure using the Bicep template in section 5.2."
```

---

**END OF SPECIFICATION**

*Generated for Karthik Subramanian | Cortex — Second Brain | April 2026*