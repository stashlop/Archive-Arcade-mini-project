
--------------------------------------------------🚧 Work in Progress

🎮 Archive & Arcade

🌟 Overview
Archive & Arcade (A-A) is an engaging platform that combines retro gaming experiences with a digital archive system. It allows users to explore classic arcade-style games while also accessing a curated collection of digital content. The project aims to preserve digital history and provide interactive entertainment.

🏛️ Features
<img width="1909" height="905" alt="Screenshot 2025-09-27 210604" src="https://github.com/user-attachments/assets/c3a2722a-a98d-48a1-a321-8601664172c3" />

<img width="1909" height="905" alt="Screenshot 2025-09-27 210649" src="https://github.com/user-attachments/assets/96ce48f2-3081-4684-beb3-478b05ac69c7" />

🎮 Arcade Mode – Play classic-inspired retro games

📂 Archive Access – Browse and search through stored digital collections

🔑 User Accounts – Registration, login, and profile management

⭐ Achievements & Scores – Track progress and compete with others

🛠️ Admin Dashboard – Manage games, archives, and users

🛠️ Technology Stack

Frontend: HTML5, CSS3, JavaScript

Backend: Python (Flask)

Database: SQLite / SQLAlchemy ORM

UI Framework: Bootstrap

Authentication: Flask-Login

📦 Installation

Clone the repository

git clone https://github.com/stashlop/A-A.git
cd A-A


Create a virtual environment & activate

python -m venv venv  
source venv/bin/activate   # macOS/Linux  
venv\Scripts\activate      # Windows


Install dependencies

pip install -r requirements.txt


Run the application

flask run


App will be available at http://localhost:5000

🗂️ Project Structure
A-A/
 ├── static/        # CSS, JS, images
 ├── templates/     # HTML templates
 ├── app.py         # Main application entry point
 ├── models.py      # Database models
 ├── requirements.txt
 └── README.md

🚀 Key Highlights

Gamification + Archiving in one platform

Responsive design for desktop & mobile

Extensible architecture for adding new games or archive sections

🔮 Future Enhancements

Multiplayer support

Advanced search & tagging in archives

Mobile-first PWA support

Cloud-based database integration

## Admin access (demo)

- A default admin user is created on first run: username `admin`, password `admin123` (override via env `ADMIN_DEFAULT_PASSWORD`).
- Alternatively, log in with any username listed in `ADMIN_USERS` (comma-separated), or the first registered user (ID 1) will be treated as admin.
- Once logged in as admin, you'll see an Admin link in the header that opens `/admin`.
