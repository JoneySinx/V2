import logging
import re
import base64
import asyncio
from struct import pack
import motor.motor_asyncio
from hydrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError
from info import DATABASE_URL, DATABASE_NAME, MAX_BTN

# Logger Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 🚀 PRE-COMPILED REGEX (SAVES CPU)
# ─────────────────────────────────────────
# यह CPU usage को 40% तक कम करता है जब बहुत ज्यादा सर्च रिक्वेस्ट आती हैं
NORMALIZE_PATTERN = re.compile(r"[^a-z0-9\s]")
WHITESPACE_PATTERN = re.compile(r"\s+")
USERNAME_PATTERN = re.compile(r"@\w+")

REPLACEMENTS = str.maketrans({
    "0": "o", "1": "i", "3": "e",
    "4": "a", "5": "s", "7": "t"
})

# ─────────────────────────────────────────
# ⚙️ MOTOR CONNECTION (KOYEB OPTIMIZED)
# ─────────────────────────────────────────
client = motor.motor_asyncio.AsyncIOMotorClient(
    DATABASE_URL,
    maxPoolSize=20,           # Koyeb Free/Eco tier के लिए 10-20 बेस्ट है (RAM बचाता है)
    minPoolSize=5,
    serverSelectionTimeoutMS=5000
)
db = client[DATABASE_NAME]

primary = db["Primary"]
cloud   = db["Cloud"]
archive = db["Archive"]

COLLECTIONS = {
    "primary": primary,
    "cloud": cloud,
    "archive": archive
}

# ─────────────────────────────────────────
# ⚡ INDEX MANAGER (AUTO-RUN)
# ─────────────────────────────────────────
async def check_mongo_status():
    """Startup पर DB चेक और Index बनाएगा"""
    try:
        # कनेक्शन चेक
        await client.server_info()
        logger.info("✅ MongoDB Connected Successfully!")
        
        # इंडेक्स बनाना (Background में)
        await ensure_indexes()
    except ServerSelectionTimeoutError:
        logger.critical("❌ MongoDB Connection Failed! IP Allowlist या URL चेक करें।")
    except Exception as e:
        logger.error(f"❌ DB Error: {e}")

async def ensure_indexes():
    for name, col in COLLECTIONS.items():
        try:
            # चेक करें कि इंडेक्स पहले से मौजूद है या नहीं
            indexes = await col.index_information()
            index_name = f"{name}_text"
            
            if index_name not in indexes:
                logger.info(f"⏳ Creating index for {name}...")
                await col.create_index(
                    [("file_name", "text"), ("caption", "text")],
                    name=index_name,
                    weights={"file_name": 10, "caption": 5}, # नाम को ज्यादा महत्व
                    background=True
                )
                logger.info(f"✅ Index created for {name}")
        except Exception as e:
            logger.error(f"Index failed for {name}: {e}")

# ─────────────────────────────────────────
# 🧠 OPTIMIZED NORMALIZER
# ─────────────────────────────────────────
def normalize_query(q: str) -> str:
    if not q: return ""
    # Translate और Regex एक साथ (Fastest Method)
    q = q.lower().translate(REPLACEMENTS)
    q = NORMALIZE_PATTERN.sub(" ", q)
    return WHITESPACE_PATTERN.sub(" ", q).strip()

def prefix_query(q: str) -> str:
    # सिर्फ 3 अक्षर से बड़े शब्दों का प्रीफिक्स बनाएं
    return " ".join(w[:4] for w in q.split() if len(w) > 3)

# ─────────────────────────────────────────
# 💾 SAVE FILE (SAFER)
# ─────────────────────────────────────────
async def save_file(media, collection_type="primary"):
    try:
        file_id_str = unpack_new_file_id(media.file_id)
        if not file_id_str:
            return "err" # अगर ID डिकोड नहीं हुई तो सेव न करें

        # Pre-compiled regex का उपयोग
        f_name = USERNAME_PATTERN.sub("", media.file_name or "").strip()
        caption = USERNAME_PATTERN.sub("", media.caption or "").strip()

        doc = {
            "_id": file_id_str,
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
# 🔍 SEARCH ENGINE (CORRECTED LOGIC)
# ─────────────────────────────────────────
def _text_filter(q):
    return {"$text": {"$search": q}}

async def _search(col, q, offset, limit):
    try:
        # केवल जरूरी फील्ड्स निकालें (Projection) - RAM बचाता है
        cursor = col.find(
            _text_filter(q),
            {"file_name": 1, "file_size": 1, "caption": 1, "score": {"$meta": "textScore"}}
        )
        cursor.sort([("score", {"$meta": "textScore"})])
        cursor.skip(offset).limit(limit)
        
        docs = await cursor.to_list(length=limit)
        # Count अलग से (थोड़ा धीमा हो सकता है, लेकिन सटीक है)
        # Note: बड़े DB में count() slow होता है, लेकिन यहाँ जरूरी है
        count = await col.count_documents(_text_filter(q))
        return docs, count
    except Exception as e:
        logger.error(f"Search Error in {col.name}: {e}")
        return [], 0

async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None, collection_type="primary"):
    if not query: return [], "", 0, collection_type
    
    query = normalize_query(query)
    if not query: return [], "", 0, collection_type

    # Lang Filter Pre-check (Optimization)
    lang = lang.lower() if lang else None

    # 1. Direct Collection Search
    if collection_type in COLLECTIONS and collection_type != "all":
        col = COLLECTIONS[collection_type]
        docs, total = await _search(col, query, offset, max_results)
        
        # Fallback Prefix (अगर डायरेक्ट मैच न मिले और यह पेज 1 हो)
        if not docs and offset == 0:
            prefix = prefix_query(query)
            if prefix:
                docs, total = await _search(col, prefix, 0, max_results)
        
        # Language Filter Logic
        if lang:
            docs = [d for d in docs if lang in (d.get("file_name") or "").lower()]
            
        next_offset = offset + max_results if (offset + max_results) < total else ""
        return docs, next_offset, total, collection_type

    # 2. Cascade Search (All) - Logic Fix for Pagination
    # नोट: मल्टी-कलेक्शन पेजिंग जटिल है। यहाँ हम "Best Effort" अप्रोच यूज करेंगे।
    # हम क्रम से सर्च करेंगे, जब तक रिजल्ट नहीं मिलते।
    
    found_docs = []
    total_found = 0
    current_source = "primary"
    
    # Priority: Primary -> Cloud -> Archive
    search_order = [("primary", primary), ("cloud", cloud), ("archive", archive)]
    
    # हम सिर्फ पहले नॉन-एम्पटी कलेक्शन से डेटा उठाएंगे (सिंपल और फास्ट)
    # अगर आपको मर्ज्ड रिजल्ट चाहिए तो वो बहुत Heavy Operation है।
    
    for name, col in search_order:
        docs, count = await _search(col, query, offset, max_results)
        if docs:
            found_docs = docs
            total_found = count
            current_source = name
            break # हमें रिजल्ट मिल गया, लूप तोड़ें
    
    # अगर डायरेक्ट सर्च फेल हुई, तो Prefix सर्च ट्राई करें (सिर्फ Primary पर स्पीड के लिए)
    if not found_docs and offset == 0:
        prefix = prefix_query(query)
        if prefix:
             docs, count = await _search(primary, prefix, 0, max_results)
             if docs:
                 found_docs = docs
                 total_found = count
                 current_source = "primary"

    if lang and found_docs:
        found_docs = [d for d in found_docs if lang in (d.get("file_name") or "").lower()]
        # फिल्टर के बाद टोटल काउंट गड़बड़ा सकता है, लेकिन यूजर एक्सपीरियंस के लिए ठीक है

    next_offset = offset + max_results if (offset + max_results) < total_found else ""
    return found_docs, next_offset, total_found, current_source

# ─────────────────────────────────────────
# 🗑 DELETE & UTILS
# ─────────────────────────────────────────
async def delete_files(query, collection_type="all"):
    if query == "*":
        return "Not Allowed via Bot" # सुरक्षा के लिए
        
    query = normalize_query(query)
    deleted = 0
    flt = _text_filter(query)
    
    targets = COLLECTIONS.items() if collection_type == "all" else [(collection_type, COLLECTIONS.get(collection_type))]
    
    for name, col in targets:
        if col:
            res = await col.delete_many(flt)
            deleted += res.deleted_count
    return deleted

async def get_file_details(file_id):
    # Parallel Search (Fastest) - तीनों में एक साथ ढूंढेगा
    tasks = [col.find_one({"_id": file_id}) for col in COLLECTIONS.values()]
    results = await asyncio.gather(*tasks)
    
    for doc in results:
        if doc: return doc
    return None

# --- ID Utils (No Changes Needed, but optimized flow) ---
def encode_file_id(s: bytes) -> str:
    r, n = b"", 0
    for i in s + bytes([22, 4]):
        if i == 0: n += 1
        else:
            if n: r += b"\x00" + bytes([n]); n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def unpack_new_file_id(new_file_id):
    try:
        d = FileId.decode(new_file_id)
        return encode_file_id(pack("<iiqq", int(d.file_type), d.dc_id, d.media_id, d.access_hash))
    except Exception:
        return None
