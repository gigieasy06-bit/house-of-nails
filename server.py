from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import bcrypt
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
BRAND = "House of Nails"

SERVICES = [
    {"id": "manicure", "name": "Manicure", "category": "unghie", "duration_min": 60, "price": 25,
     "description": "Cura completa delle mani: limatura, cuticole, idratazione e smalto classico."},
    {"id": "semipermanente", "name": "Semipermanente Rinforzato", "category": "unghie", "duration_min": 60, "price": 35,
     "description": "Unghie corte/medie, fino a tre settimane di brillantezza."},
    {"id": "copertura_gel", "name": "Copertura Unghie Gel", "category": "unghie", "duration_min": 80, "price": 45,
     "description": "Copertura in gel sull'unghia naturale per un risultato resistente."},
    {"id": "allungamento", "name": "Allungamento", "category": "unghie", "duration_min": 120, "price": 60,
     "description": "Allungamento in gel con forma a scelta."},
    {"id": "spa_mani", "name": "Spa Mani", "category": "unghie", "duration_min": 15, "price": 10,
     "description": "Trattamento rigenerante e idratante per le mani."},
    {"id": "rimozione_manicure", "name": "Rimozione + Manicure Curativa", "category": "unghie", "duration_min": 45, "price": 20,
     "description": "Rimozione delicata del prodotto e manicure curativa."},
    {"id": "pedicure_curativa", "name": "Pedicure Curativa + Semipermanente", "category": "pedicure", "duration_min": 75, "price": 45,
     "description": "Pedicure curativa completa con smalto semipermanente."},
    {"id": "semipermanente_piedi", "name": "Solo Semipermanente Piedi", "category": "pedicure", "duration_min": 45, "price": 30,
     "description": "Smalto semipermanente per i piedi."},
    {"id": "laminazione_ciglia", "name": "Laminazione Coreana Ciglia", "category": "laminazione", "duration_min": 60, "price": 60,
     "description": "Esalta le tue ciglia naturali con una curvatura personalizzata."},
    {"id": "laminazione_sopracciglia", "name": "Laminazione Coreana Sopracciglia", "category": "laminazione", "duration_min": 45, "price": 40,
     "description": "Sopracciglia ordinate e piene per settimane."},
    {"id": "combo_laminazione", "name": "Combo Laminazione Coreana Ciglia + Sopracciglia", "category": "laminazione", "duration_min": 60, "price": 80,
     "description": "Il trattamento completo per ciglia e sopracciglia in un'unica seduta."},
]

EXTRAS = [
    {"id": "french", "name": "French", "price": 5},
    {"id": "babyboomer", "name": "Babyboomer", "price": 5},
    {"id": "decorazioni", "name": "Piccole decorazioni", "price": 5},
]


def to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def day_hours(day) -> Optional[tuple]:
    """Ritorna (apertura, chiusura) in minuti, oppure None se chiuso."""
    wd = day.weekday()
    if wd == 0:  # lunedì chiuso
        return None
    if wd == 6:  # domenica: solo la prima del mese, 10:00–18:00
        return (10 * 60, 18 * 60) if day.day <= 7 else None
    return (8 * 60 + 30, 19 * 60)  # mar–sab 8:30–19:00


def slot_starts(day, duration_min: int) -> List[str]:
    hours = day_hours(day)
    if not hours:
        return []
    open_m, close_m = hours
    starts = []
    t = open_m
    while t + duration_min <= close_m:
        starts.append(f"{t // 60:02d}:{t % 60:02d}")
        t += 30
    return starts


def overlaps(day_bookings: List[dict], start_min: int, duration_min: int) -> bool:
    for b in day_bookings:
        b_start = to_min(b["time"])
        b_end = b_start + b.get("duration_min", 60)
        if start_min < b_end and b_start < start_min + duration_min:
            return True
    return False


# ---------- SMS notification ----------

def send_owner_sms(booking: dict):
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    to_number = os.environ.get("OWNER_PHONE")
    if not (sid and token and from_number and to_number):
        logger.info("Twilio non configurato: SMS non inviato per prenotazione %s", booking["id"])
        return
    try:
        from twilio.rest import Client
        day = datetime.strptime(booking["date"], "%Y-%m-%d").strftime("%d/%m/%Y")
        extras = f" Extra: {', '.join(booking['extras'])}." if booking.get("extras") else ""
        sede = f" Sede: {booking['location']}." if booking.get("location") else ""
        body = (
            f"Nuova prenotazione {BRAND}: {booking['service_name']} il {day} alle {booking['time']}.{sede}{extras} "
            f"Cliente: {booking['name']}, tel {booking['phone']}. Totale €{booking['price']}."
        )
        Client(sid, token).messages.create(to=to_number, from_=from_number, body=body)
        logger.info("SMS inviato al titolare per prenotazione %s", booking["id"])
    except Exception as e:
        logger.error("Invio SMS fallito per prenotazione %s: %s", booking["id"], e)


# ---------- Auth ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def set_auth_cookies(response: Response, user_id: str, email: str):
    response.set_cookie("access_token", create_access_token(user_id, email),
                        httponly=True, secure=True, samesite="none", max_age=900, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user_id),
                        httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token non valido")
        user = await db.users.find_one({"_id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="Utente non trovato")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")


class LoginInput(BaseModel):
    email: str
    password: str


@api_router.post("/auth/login")
async def login(input: LoginInput, response: Response):
    email = input.email.strip().lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email o password non corrette")
    set_auth_cookies(response, str(user["_id"]), email)
    return {"email": email, "name": user.get("name", "Admin"), "role": user.get("role", "admin")}


@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"email": user["email"], "name": user.get("name", "Admin"), "role": user.get("role", "admin")}


@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non autenticato")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Token non valido")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")
    user = await db.users.find_one({"_id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="Utente non trovato")
    response.set_cookie("access_token", create_access_token(str(user["_id"]), user["email"]),
                        httponly=True, secure=True, samesite="none", max_age=900, path="/")
    return {"ok": True}


# ---------- Services & availability ----------

@api_router.get("/services")
async def get_services():
    return SERVICES


@api_router.get("/extras")
async def get_extras():
    return EXTRAS


@api_router.get("/availability")
async def get_availability(date: str, service_id: str = "manicure"):
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida")
    service = next((s for s in SERVICES if s["id"] == service_id), None)
    duration = service["duration_min"] if service else 60
    starts = slot_starts(day, duration)
    if not starts:
        return {"date": date, "closed": True, "slots": []}
    existing = await db.bookings.find(
        {"date": date, "status": {"$ne": "cancellata"}}, {"_id": 0, "time": 1, "duration_min": 1}
    ).to_list(200)
    now = datetime.now()
    today = now.date()
    now_min = now.hour * 60 + now.minute
    slots = []
    for t in starts:
        sm = to_min(t)
        available = not overlaps(existing, sm, duration)
        if day < today or (day == today and sm <= now_min):
            available = False
        slots.append({"time": t, "available": available})
    return {"date": date, "closed": False, "slots": slots}


# ---------- Bookings ----------

class BookingInput(BaseModel):
    service_id: str
    date: str
    time: str
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=6, max_length=20)
    notes: Optional[str] = ""
    extras: List[str] = []
    location: str = ""


def booking_public(b: dict) -> dict:
    b.pop("_id", None)
    return b


@api_router.post("/bookings", status_code=201)
async def create_booking(input: BookingInput):
    service = next((s for s in SERVICES if s["id"] == input.service_id), None)
    if not service:
        raise HTTPException(status_code=400, detail="Servizio non valido")
    try:
        day = datetime.strptime(input.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Data non valida")
    duration = service["duration_min"]
    valid_starts = slot_starts(day, duration)
    if day_hours(day) is None:
        raise HTTPException(status_code=400, detail="In questo giorno siamo chiusi")
    if day < datetime.now().date():
        raise HTTPException(status_code=400, detail="Non puoi prenotare nel passato")
    if input.time not in valid_starts:
        raise HTTPException(status_code=400, detail="Orario non valido per questo servizio")
    extras_sel = [e for e in EXTRAS if e["id"] in input.extras]
    if len(extras_sel) != len(set(input.extras)):
        raise HTTPException(status_code=400, detail="Extra non validi")
    location = next((l for l in ("Gottolengo", "Montichiari") if l.lower() == input.location.strip().lower()), None)
    if not location:
        raise HTTPException(status_code=400, detail="Scegli una sede: Gottolengo o Montichiari")
    existing = await db.bookings.find(
        {"date": input.date, "status": {"$ne": "cancellata"}}, {"_id": 0, "time": 1, "duration_min": 1}
    ).to_list(200)
    if overlaps(existing, to_min(input.time), duration):
        raise HTTPException(status_code=409, detail="Questo orario è già occupato")
    booking = {
        "id": str(uuid.uuid4()),
        "service_id": service["id"],
        "service_name": service["name"],
        "duration_min": duration,
        "extras": [e["name"] for e in extras_sel],
        "location": location,
        "price": service["price"] + sum(e["price"] for e in extras_sel),
        "date": input.date,
        "time": input.time,
        "name": input.name.strip(),
        "phone": input.phone.strip(),
        "notes": (input.notes or "").strip(),
        "status": "in_attesa",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bookings.insert_one(booking)
    asyncio.create_task(asyncio.to_thread(send_owner_sms, booking))
    return booking_public(booking)


@api_router.get("/bookings/{booking_id}")
async def get_booking(booking_id: str):
    b = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    return b


# ---------- Calendar (.ics singolo + feed sottoscritto) ----------

def ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_vevent(b: dict) -> List[str]:
    d = b["date"].replace("-", "")
    start = f"{d}T{b['time'].replace(':', '')}00"
    end_min = to_min(b["time"]) + b.get("duration_min", 60)
    end = f"{d}T{end_min // 60:02d}{end_min % 60:02d}00"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extras = f" Extra: {', '.join(b['extras'])}." if b.get("extras") else ""
    desc = ics_escape(f"Cliente: {b['name']} - Tel: {b['phone']} -{extras} Totale EUR {b.get('price', '')} - Pagamento in sede.")
    loc = ics_escape(f"House of Nails — {b.get('location', '')}".rstrip(" —"))
    return [
        "BEGIN:VEVENT",
        f"UID:{b['id']}@houseofnails",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start}",
        f"DTEND:{end}",
        f"SUMMARY:{ics_escape(b['service_name'] + ' — ' + b['name'])}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{loc}",
        "END:VEVENT",
    ]


def wrap_vcalendar(events: List[List[str]]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//House of Nails//Prenotazioni//IT",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:House of Nails — Prenotazioni",
    ]
    for ev in events:
        lines.extend(ev)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@api_router.get("/bookings/{booking_id}/ics")
async def booking_ics(booking_id: str):
    b = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    return Response(
        content=wrap_vcalendar([make_vevent(b)]),
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="prenotazione-{b["id"][:8]}.ics"'},
    )


@api_router.get("/calendar.ics")
async def calendar_feed(token: str = ""):
    import secrets as _secrets
    expected = os.environ.get("CALENDAR_FEED_TOKEN", "")
    if not expected or not _secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Link calendario non valido")
    today = datetime.now().date().isoformat()
    items = await db.bookings.find(
        {"status": {"$ne": "cancellata"}, "date": {"$gte": today}}, {"_id": 0}
    ).sort([("date", 1), ("time", 1)]).to_list(1000)
    return Response(
        content=wrap_vcalendar([make_vevent(b) for b in items]),
        media_type="text/calendar",
        headers={"Cache-Control": "no-cache"},
    )


@api_router.get("/admin/calendar-link")
async def admin_calendar_link(request: Request, user: dict = Depends(get_current_user)):
    token = os.environ.get("CALENDAR_FEED_TOKEN", "")
    host = request.headers.get("x-forwarded-host", request.url.hostname)
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return {"url": f"{proto}://{host}/api/calendar.ics?token={token}"}


# ---------- Admin ----------

@api_router.get("/admin/bookings")
async def admin_bookings(user: dict = Depends(get_current_user)):
    items = await db.bookings.find({}, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(500)
    return items


class StatusInput(BaseModel):
    status: str


@api_router.patch("/admin/bookings/{booking_id}")
async def admin_update_booking(booking_id: str, input: StatusInput, user: dict = Depends(get_current_user)):
    if input.status not in ("in_attesa", "confermata", "cancellata"):
        raise HTTPException(status_code=400, detail="Stato non valido")
    res = await db.bookings.update_one({"id": booking_id}, {"$set": {"status": input.status}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prenotazione non trovata")
    b = await db.bookings.find_one({"id": booking_id}, {"_id": 0})
    return b


# ---------- Codice sorgente ----------

SOURCE_FILES = [
    "backend/server.py",
    "backend/requirements.txt",
    "frontend/package.json",
    "frontend/tailwind.config.js",
    "frontend/public/index.html",
    "frontend/src/index.js",
    "frontend/src/App.js",
    "frontend/src/App.css",
    "frontend/src/index.css",
    "frontend/src/components/Logo.jsx",
    "frontend/src/components/Navbar.jsx",
    "frontend/src/components/Hero.jsx",
    "frontend/src/components/Marquee.jsx",
    "frontend/src/components/Services.jsx",
    "frontend/src/components/Gallery.jsx",
    "frontend/src/components/BookingWizard.jsx",
    "frontend/src/components/Footer.jsx",
    "frontend/src/pages/Home.jsx",
    "frontend/src/pages/Admin.jsx",
    "frontend/src/pages/Codice.jsx",
]


@api_router.get("/source-code")
async def source_code():
    files = []
    for rel in SOURCE_FILES:
        path = os.path.join("/app", rel)
        if os.path.exists(path):
            with open(path, "r") as f:
                files.append({"path": rel, "content": f.read()})
    return {"files": files}


@api_router.get("/")
async def root():
    return {"message": "House of Nails API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.bookings.create_index([("date", 1), ("time", 1)])
    admin_email = os.environ["ADMIN_EMAIL"].lower()
    admin_password = os.environ["ADMIN_PASSWORD"]
    existing = await db.users.find_one({"role": "admin"})
    if existing is None:
        await db.users.insert_one({
            "_id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Anita",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Admin user seeded")
    else:
        updates = {}
        if existing["email"] != admin_email:
            updates["email"] = admin_email
        if existing.get("name") != "Anita":
            updates["name"] = "Anita"
        if updates:
            await db.users.update_one({"_id": existing["_id"]}, {"$set": updates})
            logger.info("Admin user updated")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
