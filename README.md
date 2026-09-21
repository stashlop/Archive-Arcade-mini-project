# 🎮 Archive Arcade — Final Project

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-black.svg?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20%2F%20SQLAlchemy-003B57.svg?logo=sqlite&logoColor=white)](https://sqlite.org/)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7.svg?logo=render&logoColor=white)](https://render.com)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Render%20App-brightgreen.svg)](https://archive-arcade-mini-project.onrender.com)

**Live Demo**: [https://archive-arcade-mini-project.onrender.com](https://archive-arcade-mini-project.onrender.com)

**Archive Arcade** is an end-to-end full-stack Flask web application blending an interactive multimedia Books catalog, a Video Games store with real-time cart and demo checkout, a Cafe table-booking reservation system, an Admin intelligence dashboard with revenue trends, a Community hub for announcements and profiles, and a collaborative **Knowledge Constellation** network graph and real-time chat.

---

## ✨ Features Overview

### 1. 📚 Books Catalog (`/books`)
- Filter by media type (Manga, Light Novels, Traditional Novels, Technical Books, Non-Fiction) and search by title, author, or description.
- Add items to Cart with options to **Buy** or **Rent**.
- Sleek frosted glass cards with synchronized background video.

### 2. 🕹️ Video Games Store (`/video_games`)
- Filter games by category and tags with dynamic search.
- Buy or rent games directly into the persistent cart session.
- Glassmorphic card layouts with rich game cover imagery.

### 3. 🛒 Cart, Checkout & Order Tracking (`/cart`, `/checkout`, `/history`)
- **Real-time Cart**: Add, update quantity, remove, or clear items with automatic header count updates.
- **INR Currency Conversion**: Dynamic automatic USD-to-INR conversions with currency symbol formatting.
- **Checkout (`/checkout`)**: Choose between Card, UPI, Cash-on-Delivery (COD), or Demo payment.
- **Order Lifecycle (`/history`)**: Track delivery progression (`Processing` ➔ `Out for delivery` ➔ `Delivered`).

### 4. ☕ Cafe Booking System (`/cafe`)
- Slot capacity calculation with overlap checks and duration options (30 to 240 minutes).
- Automated operating schedules (Closed Sundays, Saturday members-only notes).
- Customer portal to view and cancel personal bookings.

### 5. 🌌 Knowledge Constellation & Social Hub (`/constellation`)
- **Social Graph Visualization**: Explore connections between concepts, topics, and users in an interactive 2D node-edge constellation.
- **Private & Peer Messaging**: Send messages and exchange ideas with integrated file attachments (PDFs, images, documents).
- **Friend Requests & User Discovery**: Send, accept, or decline friend requests with dynamic user tagging (`#0000`).
- **Cloud Attachment Storage**: Optional integration with Cloudinary for persistent media uploads.

### 6. 📊 Admin Intelligence Dashboard (`/admin`)
- Metric totals: aggregate revenue, order counts, and cafe seat utilization.
- Payment method breakdown & revenue trends by day.
- Manage order status updates (`Processing`, `Out for delivery`, `Delivered`).
- Export full transaction and revenue records to CSV (`/admin/revenue.csv`).
- Seamless background video transitions (`books.mp4` ➔ `videogames.mp4`).

### 7. 👥 Community Hub (`/community`)
- Email-based subscriptions directly from the landing page without requiring immediate registration.
- Broadcast announcements feed: Admins post bulletins; community members interact.
- Member directory with privacy-masked email addresses and custom avatars.
- Profile settings: Update display names, profile avatars, and account credentials.

### 8. 📱 Cross-Device WiFi / LAN Testing (`run_local.py`)
- Automated network detection allows running the application on `0.0.0.0` to test instantly on mobile devices or other PCs over local WiFi.
- Built-in CORS support and a diagnostic endpoint at `/api/network-status`.

---

## 🧱 Tech Stack

- **Backend**: Python 3.12, Flask 3.x, Flask-SQLAlchemy, Werkzeug, Gunicorn
- **Frontend**: HTML5, Jinja2 Templates, Vanilla JavaScript, CSS3 Glassmorphism design system
- **Databases**: SQLite (multi-store instance databases), optional PostgreSQL via SQLAlchemy, optional MongoDB sync
- **Media & Assets**: Cloudinary SDK (cloud asset storage), HTML5 Video backgrounds, Spline 3D embeds

---

## 📂 Project Structure

```text
Archive-Arcade-mini-project/
├── A/                              # Media and book assets
├── A&A/                            # Core Flask application package
│   ├── static/                     # CSS stylesheets, images, video assets, uploads
│   │   ├── arcade.css              # Glassmorphic component styling
│   │   ├── style.css               # Core styling and typography
│   │   └── uploads/                # Local avatar & constellation attachments
│   ├── templates/                  # Jinja2 HTML templates
│   │   ├── admin.html              # Admin intelligence dashboard
│   │   ├── books.html              # Books catalog & filters
│   │   ├── cafe.html               # Cafe slot booking interface
│   │   ├── cart.html               # Shopping cart
│   │   ├── checkout.html           # Payment checkout flow
│   │   ├── community.html          # Community announcements & members
│   │   ├── constellation.html      # Knowledge constellation network & chat
│   │   ├── history.html            # Order history with delivery status
│   │   ├── home.html / index.html  # Landing pages
│   │   └── partials/               # Shared glass UI headers and footers
│   ├── app.py                      # Application factory, routes, and main logic
│   ├── auth.py                     # Authentication blueprint (SQLite)
│   ├── books_api.py                # Books catalog blueprint & endpoints
│   ├── cart_api.py                 # Shopping cart & checkout blueprint
│   ├── games_api.py                # Video games catalog blueprint
│   └── models.py                   # SQLAlchemy ORM models
├── instance/                       # SQLite persistent databases (seed data)
│   ├── books.db                    # Book catalog records
│   ├── cafe.db                     # Cafe bookings & reservations
│   ├── community.db                # Newsletter subscribers & community posts
│   ├── constellation.db            # Constellation nodes, edges, chats, & messages
│   ├── games.db                    # Games catalog & purchase order history
│   └── users.db                    # User accounts, passwords & profiles
├── NETWORK_TEST.md                 # Cross-device WiFi testing guide
├── render.yaml                     # Render deployment configuration
├── requirements.txt                # Python package dependencies
├── run_local.py                    # Local dev runner with LAN/WiFi IP detection
├── vercel.json                     # Vercel serverless deployment config
└── wsgi.py                         # WSGI entry point
```

---

## 📦 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/stashlop/Archive-Arcade-mini-project.git
cd Archive-Arcade-mini-project
```

### 2. Set Up Virtual Environment

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the Application

#### Option A: Quick Local / Multi-Device WiFi Runner (Recommended)
```bash
python run_local.py
```
*Prints both `http://127.0.0.1:5000` (local) and your network LAN IP (e.g. `http://192.168.x.x:5000`) for instant mobile testing.*

#### Option B: Standard Python Execution
```bash
# Linux / macOS
python A\&A/app.py

# Windows (PowerShell or Command Prompt)
python "A&A/app.py"
```

The application will be accessible at [http://127.0.0.1:5000](http://127.0.0.1:5000).

---

## 🔐 Default Demo Accounts

- **Admin Account**:
  - **Username**: `admin`
  - **Password**: `admin123`
  - *Provides access to `/admin` and community administrative broadcasts.*
- **Custom Admins**: Set the `ADMIN_USERS` environment variable as a comma-separated list of usernames to grant admin privileges.

---

## ⚙️ Environment Variables

Create a `.env` file in the project root (see `.env.example`):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SECRET_KEY` | `dev-secret-key-change-me` | Secret key for cryptographic session signing. Set securely in production! |
| `ADMIN_DEFAULT_PASSWORD` | `admin123` | Default password used when seeding the initial `admin` user. |
| `ADMIN_USERS` | `admin` | Comma-separated list of usernames granted admin status. |
| `CAFE_OPEN` | `10:00` | Cafe opening time (HH:MM). |
| `CAFE_CLOSE` | `22:00` | Cafe closing time (HH:MM). |
| `CAFE_SLOT_CAPACITY` | `10` | Maximum party seats per time slot. |
| `CAFE_DEFAULT_DURATION` | `60` | Default booking duration in minutes. |
| `USD_TO_INR` | `83` | Currency conversion rate applied across catalog items and cart totals. |
| `INSTANCE_PATH` | `./instance` | Directory for persistent SQLite databases (e.g. `/mnt/instance` on Render disk). |
| `DATABASE_URL` | *(SQLite default)* | Optional PostgreSQL database URL for SQLAlchemy models. |
| `CLOUDINARY_CLOUD_NAME` | *(optional)* | Cloudinary cloud identifier for cloud file uploads. |
| `CLOUDINARY_API_KEY` | *(optional)* | Cloudinary API Key. |
| `CLOUDINARY_API_SECRET` | *(optional)* | Cloudinary API Secret. |
| `MONGODB_URI` | *(optional)* | Optional MongoDB connection string for hybrid database sync. |

---

## 🚀 Deployment

### Deploy on Render (Recommended)
This repository includes a pre-configured [`render.yaml`](render.yaml) blueprint:
1. Connect your repository on [Render](https://dashboard.render.com/).
2. Attach a Persistent Disk mounted at `/mnt/instance` to retain database state across restarts.
3. Configure `INSTANCE_PATH = /mnt/instance` in your Render Environment Variables.

### Deploy on Vercel
Configured via [`vercel.json`](vercel.json) using [`wsgi.py`](wsgi.py) as a serverless function handler. In serverless environments with read-only filesystems, storage automatically falls back to `/tmp`.

---

## 🛠️ Issue Tracking & Roadmap

Active development tasks and tracked bugs are logged on GitHub:

- **[#2](https://github.com/stashlop/Archive-Arcade-mini-project/issues/2)**: [Bug] Session key mismatch between auth blueprint and cart/purchases APIs leads to 401 Unauthorized
- **[#3](https://github.com/stashlop/Archive-Arcade-mini-project/issues/3)**: [Architecture / Bug] Constellation feature database mismatch: SQLAlchemy models target users.db while queries target constellation.db
- **[#4](https://github.com/stashlop/Archive-Arcade-mini-project/issues/4)**: [Security] Insecure fallback SECRET_KEY and hardcoded production secret in render.yaml
- **[#5](https://github.com/stashlop/Archive-Arcade-mini-project/issues/5)**: [Concurrency / Bug] Race condition in Cafe booking allows slot overbooking beyond capacity
- **[#6](https://github.com/stashlop/Archive-Arcade-mini-project/issues/6)**: [Security] Missing CSRF protection on state-changing HTML forms and API routes
- **[#7](https://github.com/stashlop/Archive-Arcade-mini-project/issues/7)**: [Architecture] Consolidate multi-database SQLite architecture and implement database migrations
- **[#8](https://github.com/stashlop/Archive-Arcade-mini-project/issues/8)**: [Security / Reliability] Enforce MAX_CONTENT_LENGTH and strict MIME validation on file uploads
- **[#9](https://github.com/stashlop/Archive-Arcade-mini-project/issues/9)**: [CI/CD & Testing] Add automated test suite (Pytest) and GitHub Actions CI workflow

---

## 📄 License

This project is developed for educational and demonstration purposes. Contributions, feedback, and pull requests are welcome!
