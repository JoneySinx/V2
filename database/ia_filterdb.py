import logging
import re
import base64
from struct import pack
import motor.motor_asyncio
from hydrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from info import DATABASE_URL, DATABASE_NAME, MAX_BTN

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# ⚙️ MOTOR ASYNC CONNECTION
# ─────────────────────────────────────────
client = motor.motor_asyncio.AsyncIOMotorClient(
    DATABASE_URL,
    maxPoolSize=50,
    minPoolSize=10,
    serverSelectionTimeoutMS=5000
)
db = client[DATABASE_NAME]

# Media = Collection (Used for 'Import Error' fix)
Media = db["Primary"] 

primary = db["Primary"]
cloud   = db["Cloud"]
archive = db["Archive"]

COLLECTIONS = {
    "primary": primary,
    "cloud": cloud,
    "archive": archive
}

# ─────────────────────────────────────────
# 🛠 UTILS: FILE ID DECODING (FIXED)
# ─────────────────────────────────────────
def encode_file_id(s: bytes) -> str:
    """Encode bytes to URL-safe base64 string"""
    r = b""
    r += pack("<ii", s.major, s.minor)
    if s.file_reference:
        r += pack("<i", len(s.file_reference))
        r += s.file_reference
    r += pack("<ii", s.file_type, s.dc_id)
    if s.photo_size_source:
        r += pack("<i", s.photo_size_source)
    if s.photo_size_type:
        r += pack("<i", s.photo_size_type)
    r += pack("<ii", s.volume_id, s.local_id)
    if s.access_hash:
        r += pack("<q", s.access_hash)
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    """Return unique file_id string from Hydrogram FileId"""
    try:
        decoded = FileId.decode(new_file_id)
        file_id = encode_file_id(decoded)
        return file_id
    except Exception as e:
        logger.error(f"File ID Decode Error: {e}")
        return None

# ─────────────────────────────────────────
# ⚡ INDEXES (BACKGROUND)
# ─────────────────────────────────────────
async def ensure_indexes():
    """Create text indexes for fast search"""
    for name, col in COLLECTIONS.items():
        try:
            await col.create_index(
                [("file_name", "text"), ("caption", "text")],
                name=f"{name}_text",
                background=True
            )
        except Exception as e:
            logger.error(f"Index creation failed for {name}: {e}")

# ─────────────────────────────────────────
# 🧠 FAST NORMALIZER
# ─────────────────────────────────────────
REPLACEMENTS = str.maketrans({
    "0": "o", "1": "i", "3": "e",
    "4": "a", "5": "s", "7": "t"
})

def normalize_query(q: str) -> str:
    q = q.lower().translate(REPLACEMENTS)
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    return re.sub(r"\s+", " ", q).strip()

def prefix_query(q: str) -> str:
    return " ".join(w[:4] for w in q.split() if len(w) >= 3)

# ─────────────────────────────────────────
# 📊 DB STATS
# ─────────────────────────────────────────
async def db_count_documents():
    try:
        p = await primary.estimated_document_count()
        c = await cloud.estimated_document_count()
        a = await archive.estimated_document_count()
        return {
            "primary": p,
            "cloud": c,
            "archive": a,
            "total": p + c + a
        }
    except Exception as e:
        logger.error(f"Error counting documents: {e}")
        return {"primary": 0, "cloud": 0, "archive": 0, "total": 0}

# ─────────────────────────────────────────
# 💾 SAVE FILE
# ─────────────────────────────────────────
async def save_file(media, collection_type="primary"):
    try:
        file_id = unpack_new_file_id(media.file_id)
        if not file_id: return "err"
        
        f_name = re.sub(r"@\w+", "", media.file_name or "").strip()
        caption = re.sub(r"@\w+", "", media.caption or "").strip()

        doc = {
            "_id": file_id,
            "file_id": media.file_id,  # Store original too for safety
            "file_name": f_name,
            "caption": caption,
            "file_size": media.file_size
        }

        col = COLLECTIONS.get(collection_type, primary)
        await col.insert_one(doc)
        return "suc"
    except DuplicateKeyError:
        return "dup"
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        return "err"

# ─────────────────────────────────────────
# 🔍 SEARCH CORE
# ─────────────────────────────────────────
def _text_filter(q):
    return {"$text": {"$search": q}}

async def _search(col, q, offset, limit):
    try:
        cursor = col.find(
            _text_filter(q),
            {"file_name": 1, "file_size": 1, "caption": 1, "file_id": 1, "score": {"$meta": "textScore"}}
        )
        cursor.sort([("score", {"$meta": "textScore"})])
        cursor.skip(offset).limit(limit)
        
        docs = await cursor.to_list(length=limit)
        count = await col.count_documents(_text_filter(q))
        return docs, count
    except Exception as e:
        logger.error(f"Search error: {e}")
        return [], 0

# ─────────────────────────────────────────
# 🚀 PUBLIC SEARCH API
# ─────────────────────────────────────────
async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, collection_type="primary"):
    if not query or not query.strip():
        return [], "", 0, collection_type
    
    query = normalize_query(query)
    if not query:
        return [], "", 0, collection_type
    
    prefix = prefix_query(query)
    results = []
    total = 0
    actual_source = collection_type

    # ⚡ ASYNC CASCADE
    if collection_type == "all":
        # 1. Primary
        docs, cnt = await _search(primary, query, offset, max_results)
        if docs:
            results.extend(docs)
            total += cnt
            actual_source = "primary"
        
        # 2. Cloud
        if not results:
            docs, cnt = await _search(cloud, query, offset, max_results)
            if docs:
                results.extend(docs)
                total += cnt
                actual_source = "cloud"
            
            # 3. Archive
            if not results:
                docs, cnt = await _search(archive, query, offset, max_results)
                if docs:
                    results.extend(docs)
                    total += cnt
                    actual_source = "archive"
                
                # 4. Fallback
                if not results and prefix:
                    for col_name, col in COLLECTIONS.items():
                        docs, cnt = await _search(col, prefix, 0, max_results)
                        if docs:
                            results.extend(docs)
                            total += cnt
                            actual_source = col_name
                            break

    # Single DB Search
    elif collection_type in COLLECTIONS:
        col = COLLECTIONS[collection_type]
        docs, cnt = await _search(col, query, offset, max_results)
        results.extend(docs)
        total += cnt
        
        if not results and prefix:
            docs, cnt = await _search(col, prefix, 0, max_results)
            results.extend(docs)
            total += cnt
            
    else:
        docs, cnt = await _search(primary, query, offset, max_results)
        results.extend(docs)
        total += cnt

    if lang and results:
        lang = lang.lower()
        results = [f for f in results if lang in f["file_name"].lower()]
        total = len(results)

    next_offset = offset + max_results
    if next_offset >= total:
        next_offset = ""

    return results, next_offset, total, actual_source

# ─────────────────────────────────────────
# 🗑 DELETE FILES
# ─────────────────────────────────────────
async def delete_files(query, collection_type="all"):
    deleted = 0
    try:
        if query == "*":
            for name, col in COLLECTIONS.items():
                if collection_type != "all" and name != collection_type: continue
                res = await col.delete_many({})
                deleted += res.deleted_count
            return deleted
        
        query = normalize_query(query)
        if not query: return 0
        
        flt = _text_filter(query)
        for name, col in COLLECTIONS.items():
            if collection_type != "all" and name != collection_type: continue
            res = await col.delete_many(flt)
            deleted += res.deleted_count

        return deleted
    except Exception as e:
        logger.error(f"Error deleting: {e}")
        return deleted

# ─────────────────────────────────────────
# 📂 FILE DETAILS
# ─────────────────────────────────────────
async def get_file_details(file_id):
    try:
        for col in COLLECTIONS.values():
            doc = await col.find_one({"_id": file_id})
            if doc: return doc
        return None
    except Exception:
        return None

