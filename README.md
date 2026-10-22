# House of Nails · di Anita — Codice sorgente completo

Sito di prenotazioni online per il centro estetico: listino servizi, prenotazione con scelta di servizio, extra, data, orario e sede (Gottolengo / Montichiari), area riservata admin, sincronizzazione automatica con il Calendario iPhone, notifica SMS al titolare (opzionale).

**Nessuna dipendenza da Emergent o da servizi a pagamento obbligatori.**

---

## 1. Struttura del progetto

```
house-of-nails/
├── README.md                     ← questo file
├── .gitignore
├── backend/                      ← API (Python + FastAPI)
│   ├── server.py                 ← tutta la logica: prenotazioni, orari, auth, calendario, SMS
│   ├── requirements.txt          ← dipendenze Python
│   └── .env.example              ← variabili d'ambiente da configurare (copialo in .env)
└── frontend/                     ← Sito (React)
    ├── package.json              ← dipendenze Node
    ├── yarn.lock                 ← versioni esatte delle dipendenze
    ├── craco.config.js           ← configurazione build (alias @/ = src/)
    ├── jsconfig.json             ← alias import
    ├── tailwind.config.js        ← colori e font del design
    ├── postcss.config.js
    ├── components.json           ← configurazione shadcn/ui
    ├── .env.example              ← variabile d'ambiente frontend (copialo in .env)
    ├── public/                   ← immagini e pagina HTML base
    │   ├── index.html
    │   ├── logo.png              ← logo House of Nails
    │   ├── lavoro1-3.jpeg        ← foto reali dei lavori
    │   ├── nuovo1-4.jpeg         ← foto listino e lavori (prima/dopo)
    │   └── favicon.svg
    └── src/
        ├── index.js              ← entry point React
        ├── index.css             ← stili globali, palette, font, marquee
        ├── App.css
        ├── App.js                ← rotte: / · /admin · /codice
        ├── pages/
        │   ├── Home.jsx          ← pagina principale
        │   ├── Admin.jsx         ← area riservata (login + gestione prenotazioni)
        │   └── Codice.jsx        ← pagina "codice sorgente" con copia tutto
        ├── components/
        │   ├── Logo.jsx          Navbar.jsx    Hero.jsx       Marquee.jsx
        │   ├── Services.jsx      ← listino prezzi
        │   ├── Gallery.jsx       ← galleria foto
        │   ├── BookingWizard.jsx ← prenotazione in 5 passi
        │   ├── Footer.jsx
        │   └── ui/               ← componenti shadcn/ui (46 file)
        ├── hooks/use-toast.js
        ├── lib/utils.js
        └── constants/testIds/
```

## 2. Servizi esterni usati (tutti con piano gratuito)

| Servizio | A cosa serve | Obbligatorio? | Alternativa gratuita |
|---|---|---|---|
| MongoDB | database prenotazioni e admin | Sì | MongoDB Atlas M0 (gratis) oppure MongoDB in locale |
| Twilio | SMS al titolare a ogni prenotazione | No (se assente gli SMS vengono saltati) | twilio.com — trial gratuito |
| Calendario iPhone | feed `GET /api/calendar.ics?token=...` | Incluso nel backend | nessuna configurazione: funziona da solo |
| Google Fonts | font Cormorant Garamond + Outfit | Sì (gratis) | già incluso via CDN |

Non vengono usati Emergent LLM key, Emergent Auth, né altri servizi proprietari.

## 3. Requisiti

- Node.js 18 o superiore + yarn (`npm install -g yarn`)
- Python 3.11 o superiore
- Un database MongoDB (vedi passo 4)

## 4. Database gratuito: MongoDB Atlas

1. Vai su https://cloud.mongodb.com e crea un account gratuito
2. Crea un cluster **M0 (gratuito)**
3. Database Access → aggiungi un utente con password
4. Network Access → Allow access from anywhere (`0.0.0.0/0`)
5. Connect → Drivers → copia la stringa di connessione: sarà il tuo `MONGO_URL`

Per provare in locale invece: installa MongoDB Community e usa `MONGO_URL="mongodb://localhost:27017"`.

## 5. Avvio in locale

**Backend** (terminale 1):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # su Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # poi modifica .env con i tuoi valori
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```
Al primo avvio viene creato automaticamente l'utente admin con `ADMIN_EMAIL` e `ADMIN_PASSWORD` del file `.env`.

**Frontend** (terminale 2):
```bash
cd frontend
yarn install
cp .env.example .env      # imposta REACT_APP_BACKEND_URL=http://localhost:8001
yarn start
```
Apri http://localhost:3000 — area riservata su http://localhost:3000/admin

## 6. Variabili d'ambiente da configurare

**backend/.env** (valori mai da pubblicare):

| Variabile | Significato |
|---|---|
| `MONGO_URL` | stringa di connessione MongoDB |
| `DB_NAME` | nome del database (es. `house_of_nails`) |
| `CORS_ORIGINS` | domini del frontend, separati da virgola |
| `JWT_SECRET` | stringa casuale lunga per i token di sessione |
| `CALENDAR_FEED_TOKEN` | stringa casuale lunga: protegge il link del calendario |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | credenziali dell'area riservata |
| `OWNER_PHONE` | numero che riceve gli SMS (formato +39...) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | opzionali, per gli SMS |

Genera le stringhe casuali con: `openssl rand -hex 32`

**frontend/.env**:

| Variabile | Significato |
|---|---|
| `REACT_APP_BACKEND_URL` | URL pubblico del backend, senza slash finale |

## 7. Pubblicazione gratuita (senza Emergent)

**Backend su Render (gratis):**
1. Carica il progetto su GitHub (vedi passo 8)
2. https://render.com → New → Web Service → collega il repo
3. Root directory: `backend` — Build: `pip install -r requirements.txt` — Start: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. In Environment aggiungi tutte le variabili di `backend/.env` (con `CORS_ORIGINS` = URL del frontend)
5. Avvia e annota l'URL assegnato (es. `https://house-of-nails.onrender.com`)

**Frontend su Netlify o Vercel (gratis):**
1. New site → collega lo stesso repo
2. Root directory: `frontend` — Build command: `yarn build` — Publish directory: `build`
3. Variabile d'ambiente: `REACT_APP_BACKEND_URL` = URL del backend di Render
4. Nel backend aggiorna `CORS_ORIGINS` con l'URL del sito Netlify/Vercel

**Importante per login e area admin:** i cookie di sessione richiedono HTTPS: sia Render che Netlify/Vercel lo forniscono gratis in automatico.

## 8. Caricamento su GitHub

```bash
cd house-of-nails
git init
git add .
git commit -m "House of Nails — sito prenotazioni"
git branch -M main
git remote add origin https://github.com/TUO-UTENTE/house-of-nails.git
git push -u origin main
```
Il file `.gitignore` esclude già `.env`, `node_modules` e le build: nessun segreto finirà online.

## 9. Dopo la pubblicazione

1. Apri `https://TUO-SITO/admin` e accedi con le credenziali che hai scelto in `.env`
2. Copia il link "Sincronizza con l'iPhone di Anita" dal pannello admin
3. Sull'iPhone: Impostazioni → App → Calendario → Account Calendario → Aggiungi account → Altro → Aggiungi calendario sottoscritto → incolla il link → Salva
4. Le prenotazioni esistenti non vengono migrate automaticamente: per trasferirle, esporta la collezione `bookings` dal vecchio database (MongoDB Compass → Export) e importala nel nuovo cluster Atlas

## 10. Modifiche rapide che potresti voler fare

- **Prezzi / servizi / durate**: lista `SERVICES` in `backend/server.py` (e specchio grafico in `frontend/src/components/Services.jsx`)
- **Orari e giorni di apertura**: funzione `day_hours()` in `backend/server.py`
- **Sedi**: lista `LOCATIONS` in `frontend/src/components/BookingWizard.jsx` e validazione in `create_booking` nel backend
- **Extra (+€5)**: lista `EXTRAS` in `backend/server.py`
- **Colori e font**: `frontend/tailwind.config.js` e `frontend/src/index.css`
