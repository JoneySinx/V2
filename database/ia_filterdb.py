import logging
import re
import base64
from struct import pack
import motor.motor_asyncio
from hydrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from bson.objectid import ObjectId
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

# Collections
primary = db["Primary"]
cloud   = db["Cloud"]
archive = db["Archive"]

# For commands.py import compatibility
Media = primary 

COLLECTIONS = {
    "primary": primary,
    "cloud": cloud,
    "archive": archive
}

# ─────────────────────────────────────────
# 🛠 UTILS: FILE ID DECODING
# ─────────────────────────────────────────
def encode_file_id(s: bytes) -> str:
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
    try:
        decoded = FileId.decode(new_file_id)
        file_id = encode_file_id(decoded)
        return file_id
    except Exception as e:
        logger.error(f"Decode Error: {e}")
        return None

# ─────────────────────────────────────────
# 🧠 SMART GET FILE DETAILS (The Fix)
# ─────────────────────────────────────────
async def get_file_details(file_id):
    """
    Searches for a file in ALL collections using both String and ObjectId.
    """
    for col_name, col in COLLECTIONS.items():
        # 1. Try Exact String Match
        doc = await col.find_one({"_id": file_id})
        if doc: return doc
        
        # 2. Try ObjectId Match (For older files)
        try:
            doc = await col.find_one({"_id": ObjectId(file_id)})
            if doc: return doc
        except: pass
        
    return None

# ─────────────────────────────────────────
# 📊 DB STATS
# ─────────────────────────────────────────
async def db_count_documents():
    try:
        p = await primary.estimated_document_count()
        c = await cloud.estimated_document_count()
        a = await archive.estimated_document_count()
        return {"primary": p, "cloud": c, "archive": a, "total": p + c + a}
    except:
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
            "file_id": media.file_id,
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
        logger.error(f"Save Error: {e}")
        return "err"

# ─────────────────────────────────────────
# 🔍 SEARCH CORE
# ─────────────────────────────────────────
def _text_filter(q):
    return {"$text": {"$search": q}}

async def _search(col, q, offset, limit):
    try:
        cursor = col.find(_text_filter(q))
        cursor.sort([("score", {"$meta": "textScore"})])
        cursor.skip(offset).limit(limit)
        return await cursor.to_list(length=limit), await col.count_documents(_text_filter(q))
    except:
        return [], 0

# ─────────────────────────────────────────
# 🚀 PUBLIC SEARCH API
# ─────────────────────────────────────────
def normalize_query(q):
    return re.sub(r"[^a-z0-9\s]", " ", q.lower()).strip()

async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, collection_type="primary"):
    if not query: return [], "", 0, collection_type
    
    query = normalize_query(query)
    results, total, actual_source = [], 0, collection_type
    
    # Cascade Search
    if collection_type == "all":
        for name, col in COLLECTIONS.items():
            docs, cnt = await _search(col, query, offset, max_results)
            if docs:
                results.extend(docs)
                total += cnt
                actual_source = name
                break
    elif collection_type in COLLECTIONS:
        docs, cnt = await _search(COLLECTIONS[collection_type], query, offset, max_results)
        results.extend(docs)
        total += cnt
    
    next_offset = offset + max_results if (offset + max_results) < total else ""
    return results, next_offset, total, actual_source

# ─────────────────────────────────────────
# 🗑 DELETE FILES
# ─────────────────────────────────────────
async def delete_files(query, collection_type="all"):
    deleted = 0
    if query == "*":
        for name, col in COLLECTIONS.items():
            if collection_type == "all" or name == collection_type:
                res = await col.delete_many({})
                deleted += res.deleted_count
        return deleted
    
    query = normalize_query(query)
    flt = _text_filter(query)
    for name, col in COLLECTIONS.items():
        if collection_type == "all" or name == collection_type:
            res = await col.delete_many(flt)
            deleted += res.deleted_count
    return deleted

# ─────────────────────────────────────────
# ⚡ INDEXES
# ─────────────────────────────────────────
async def ensure_indexes():
    for name, col in COLLECTIONS.items():
        try: await col.create_index([("file_name", "text")], name=f"{name}_text", background=True)
        except: pass

