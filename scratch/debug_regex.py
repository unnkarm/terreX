import re

query = "water bodies and rivers within 5km of Biswa Bangla Gate with clear sky"
sem_text = query

# 1. Remove clear sky
sem_text = re.sub(r"clear\s+sky(?:\s+only)?", "", sem_text, flags=re.IGNORECASE)
print("After clear sky:", repr(sem_text))

# 2. Remove location
loc = "Biswa Bangla Gate"
sem_text = re.sub(re.escape(loc), "", sem_text, flags=re.IGNORECASE)
print("After loc:", repr(sem_text))

# 3. Remove distance
sem_text = re.sub(r"\b(?:within|inside|at\s+most)\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers|m|meters)?(?:\s+of)?\b", "", sem_text, flags=re.IGNORECASE)
print("After dist:", repr(sem_text))

# 4. Clean dangling prepositions
sem_text = re.sub(r"\b(?:near|close to|along|beside|adjacent to|around|in|of|on|from|with|at|under|over)\b", " ", sem_text, flags=re.IGNORECASE)
print("After prepositions:", repr(sem_text))

sem_text = re.sub(r"[,\.;:\-_]+", " ", sem_text)
sem_text = re.sub(r"\s+", " ", sem_text).strip()
print("Final sem_text:", repr(sem_text))
