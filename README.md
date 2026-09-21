# Arcade — Final Project
live link https://archive-arcade-mini-project.onrender.com
An end-to-end Flask app that blends a curated Books catalog, a Video Games shop with cart and demo checkout, a Cafe booking system, an Admin dashboard with revenue insights, and a Community page for email-based joining and admin updates. Modern glass UI with background videos and a unified header across pages.

## ✨ Features

- Accounts and access
	- Signup, login, logout. Shared glass UI header across all pages.
	- Admin detection: username `admin`, first user (ID=1), or usernames in env `ADMIN_USERS`.
	- Header greets logged-in users by display name if set.

- Books catalog (`/books`)
	- Filter by category and search by title/author/description.
	- Add to cart (Buy or Rent). Background video and glass cards.
<img width="1518" height="906" alt="Screenshot 2025-10-27 223130" src="https://github.com/user-attachments/assets/a04c7548-62b0-43ae-99fa-1e3ae5be1018" />

- Video games shop (`/video_games`)
	- Tag-style categories, search, add to cart (Buy or Rent).
	- Background video and glass cards UI.
<img width="1913" height="905" alt="Screenshot 2025-10-27 224003" src="https://github.com/user-attachments/assets/651a8453-1a3d-4bf4-87d8-bd8bea930283" />

- Cart, checkout, and history
	- Cart: add/remove/clear, dynamic header count.
	- Checkout (`/checkout`): choose Card/UPI/COD/Demo; persisted to `purchase_history` in `instance/games.db`.
	- History (`/history`): view past purchases.

- Cafe system (`/cafe`)
	- Availability rules: Sunday closed; Saturday members-only note.
	- Slot listing with capacity and default durations; booking with overlap checks.
	- View/cancel “My Bookings.” Frosted black glass visuals.
<img width="1910" height="906" alt="Screenshot 2025-10-27 224019" src="https://github.com/user-attachments/assets/e2e82065-9609-401f-9045-c50f5454ec83" />

- Admin dashboard (`/admin`)
	- Totals, revenue by payment method, revenue by day (trend bars).
	- Purchase list with method tags; cafe bookings; derived members ranking.
	- CSV export at `/admin/revenue.csv`.
	- Background videos play sequentially on admin: `books.mp4` → `videogames.mp4`.

- Community page (`/community`)
	- Join via email from Home; no login required. Stores `community_email` in session.
	- Updates feed: admins can post; all members can read.
	- Members panel: lists subscribers (emails masked for non-admins) with avatars.
	- Profile: set display name and upload photo; mirrored to User account if logged in.
	- Logged-in users can change account username.
<img width="1465" height="894" alt="Screenshot 2025-10-27 223105" src="https://github.com/user-attachments/assets/5a3e0ad7-31b3-48d1-8ab0-420e4bfe92b3" />


## 🧱 Tech Stack

- Python 3.12, Flask 3.x
- Flask-SQLAlchemy for `users.db` (User model)
- SQLite (raw) for `books.db`, `games.db` (purchase history), `cafe.db`, `community.db`
- HTML + Jinja2 templates, CSS glass design, small vanilla JS

## 📦 Setup

1) Clone and enter the project

```bash
git clone https://github.com/stashlop/Archive-Arcade-mini-project.git
cd Archive-Arcade-mini-project
```

2) Create a virtual environment and install deps

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows (PowerShell)

pip install -r requirements.txt
```

3) Run the app (note: folder name contains an ampersand)

```bash
python A\&A/app.py  # Linux/macOS
# python "A&A/app.py"  # Windows
```

The app will start on http://127.0.0.1:5000 by default.

## � Admin access (demo)

- Default admin seeded on first run:
	- Username: `admin`
	- Password: `admin123`
- You can also set:
	- `ADMIN_DEFAULT_PASSWORD` to change the default admin password.
	- `ADMIN_USERS` as a comma-separated list of additional admin usernames.
- Admin-only pages and actions require login; an “Admin” link appears in the header when admin.

## ⚙️ Environment variables (optional)

- `SECRET_KEY`: Flask secret (default: `dev-secret-key-change-me`)
- `ADMIN_DEFAULT_PASSWORD`: seed password for admin
- `ADMIN_USERS`: comma-separated usernames to grant admin
- Cafe settings:
	- `CAFE_OPEN` (default `10:00`)
	- `CAFE_CLOSE` (default `22:00`)
	- `CAFE_SLOT_STEP_MIN` (default `60`)
	- `CAFE_DEFAULT_DURATION` (default `60`)
	- `CAFE_SLOT_CAPACITY` (default `10`)

- Currency & pricing:
	- `USD_TO_INR` — conversion rate used by the Jinja `inr` filter (default `83`). Catalog base prices (stored in USD) convert at render time; cart line item unit prices and purchase totals are stored already converted to INR.

- Persistence:
	- `INSTANCE_PATH` — override Flask instance folder path (e.g. `/var/data/arcade-instance`) for deployments needing persistent disks.

## 🗄️ Data storage

All databases live under `instance/` and are created automatically on first use:

- `users.db` — Flask-SQLAlchemy User table (username, password_hash, display_name, photo_path)
- `books.db` — books catalog (seeded on first run)
- `games.db` — purchase_history (writes on checkout)
- `cafe.db` — cafe_bookings
- `community.db` — community_subscribers, community_messages

Purchase history now includes a `delivery_status` column with lifecycle values:

- `Processing` (default when order is created)
- `Out for delivery`
- `Delivered` (admin endpoint maps `Success`/`Successful` inputs to `Delivered`)

Admins update status via the dashboard dropdown; users see a status badge beside each order in `/history`.

User-uploaded avatars are saved under `static/uploads/community/`.

## 🌐 Main pages

- `/` — About (background video)
- `/books` — Books library (filters + add to cart)
- `/video_games` — Video games (filters + add to cart)
- `/cart` — Cart
- `/checkout` — Choose payment method & complete demo purchase
- `/history` — Purchase history
- `/cafe` — Book slots; view/cancel your bookings
- `/admin` — Dashboard (admins)
- `/community` — Community updates, profile, members; admins can post

## 🔌 API endpoints (selected)

- Cart (`/api/cart/*`): `GET /`, `POST /add`, `POST /remove`, `POST /clear`, `POST /checkout`
- Cafe:
	- `GET /api/cafe/availability?date=YYYY-MM-DD`
	- `GET /api/cafe/slots?date=YYYY-MM-DD`
	- `POST /api/cafe/book` { date, time, partySize, duration, note }
	- `GET /api/cafe/bookings` (mine)
	- `DELETE /api/cafe/bookings/<id>`
- Community:
	- `POST /community/join` { email }
	- `GET /api/community/messages` (list)
	- `POST /api/community/messages` (admin-only)
	- `GET /api/community/subscribers` (masked emails for non-admins)
	- `POST /community/profile` (multipart: display_name, photo)
	- `GET /api/community/me`
	- `POST /account/username` { username } (logged-in users)
- Admin:
	- `GET /admin`
	- `GET /admin/revenue.csv`

## ♻️ Resetting data

To reset all local databases (they’ll recreate on next run):

```bash
rm -f instance/*.db
```

Optionally clear uploaded avatars:

```bash
rm -f A\&A/static/uploads/community/*  # Linux/macOS
# del "A&A\static\uploads\community\*"  # Windows
```

## 🧭 Notes & tips

- Background videos: `books.mp4`, `videogames.mp4`, and `about.mp4` are used across pages; admin page plays books → videogames in sequence.
- The app self-heals missing DB columns (for safe upgrades) and seeds defaults on first run.
- Because the app folder has an ampersand (`A&A`), prefer running with the direct Python path as shown above.

## ✅ Status

This is a complete, runnable demo showcasing catalog + commerce flow (with INR conversion and delivery status tracking), bookings, admin dashboards, and community messaging with profiles, wrapped in a cohesive glass UI.
