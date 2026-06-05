# 🔥 IP Warmup Automation Tool

A production-ready web application that automates email IP warmup by logging into
each email account, finding your target email by subject line, and clicking links —
then generating a full audit report.

---

## 📋 Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or higher |
| pip | (comes with Python) |
| Internet connection | For Playwright Chromium download |

---

## 🚀 Quick Start

### Windows
```
Double-click  START_WINDOWS.bat
```
That's it. It will install everything and open the server.

### Mac / Linux
```bash
chmod +x start_mac_linux.sh
./start_mac_linux.sh
```

### Manual setup (any OS)
```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate it
#    Windows:
venv\Scripts\activate
#    Mac/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser
python -m playwright install chromium

# 5. Start the server
python app.py
```

Then open **http://localhost:5000** in your browser.

---

## 📁 Project Structure

```
ipwarmup/
├── app.py                  ← Flask backend (API + routing)
├── automation.py           ← Playwright browser automation engine
├── requirements.txt        ← Python dependencies
├── generate_sample.py      ← Generate a test Excel file
├── START_WINDOWS.bat       ← One-click start for Windows
├── start_mac_linux.sh      ← One-click start for Mac/Linux
├── templates/
│   └── index.html          ← Full frontend UI
├── uploads/                ← Uploaded Excel files (auto-created)
└── reports/                ← Exported reports (auto-created)
```

---

## 📊 Excel File Format

Your credentials file must have these columns:

| Column | Required | Description |
|--------|----------|-------------|
| `email` | ✅ Yes | Full email address |
| `password` | ✅ Yes | Account password |
| `subject_line` | ❌ Optional | Per-account override subject |

**Generate a sample file:**
```bash
python generate_sample.py
```

---

## 🌐 Supported Email Providers

| Provider | Domain(s) | Auto-detected |
|----------|-----------|---------------|
| Gmail | gmail.com, googlemail.com | ✅ |
| Outlook | outlook.com, hotmail.com, live.com, msn.com | ✅ |
| Yahoo Mail | yahoo.com, yahoo.co.in, ymail.com | ✅ |
| ProtonMail | protonmail.com, proton.me | ✅ |
| iCloud Mail | icloud.com, me.com, mac.com | ✅ |
| Zoho Mail | zoho.com | ✅ |
| AOL | aol.com | ✅ |
| Corporate / Custom | any other domain | ✅ (best-effort) |

---

## ⚙️ Configuration Options

| Setting | Options | Default |
|---------|---------|---------|
| Global subject line | Any text | (required) |
| Search folder | Inbox / Promotions / Spam / All | Inbox |
| If found in spam | Move to inbox / Open in spam | Move to inbox |
| Min links to click | 2 / 3 / 4 / 5 | 2 |
| Delay between accounts | 3s / 5s / 10s / 15s / 30s | 5s |
| Browser mode | Headless / Visible | Headless |

---

## 📈 Report Fields

Every row in the exported report contains:

- **Email** — the account email address
- **Domain** — email domain
- **Provider** — detected provider name
- **Subject** — the subject used for this account
- **Login OK** — whether login succeeded
- **Email Found** — whether the target email was found
- **In Spam** — whether email was in spam folder
- **Links Clicked** — number of links clicked
- **Status** — Success / Partial / Failed
- **Note** — human-readable outcome description
- **Timestamp** — when the run completed

Export as **CSV** or **JSON** from the Report tab.

---

## 🔒 Security Notes

- Passwords are never stored on disk — they live only in memory during the run
- The tool runs entirely locally on your machine
- No data is sent to any external server (only to the email providers themselves)
- Use app passwords where 2FA is enabled (Gmail → App Passwords, Outlook → App Passwords)

---

## 💡 Tips for Best Results

1. **2FA accounts** — Generate an App Password and use that instead of your main password
2. **Gmail** — Enable "Less secure app access" or use App Passwords
3. **Rate limiting** — Use 10–15s delay for large lists to avoid triggering bot detection
4. **Visible mode** — Run with "Visible browser" on your first test to see exactly what happens
5. **Subject line** — Must match the email subject exactly (or at least key words)

---

## 🛠 Troubleshooting

| Issue | Fix |
|-------|-----|
| `playwright not found` | Run `python -m playwright install chromium` |
| Login fails every time | Check credentials, disable 2FA, or use App Passwords |
| Email not found | Check subject line matches exactly; try "Search everywhere" |
| Browser blocked | Switch to headless mode; add longer delays |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |

---

## 📞 Running in Demo Mode

If Playwright is not installed, the tool automatically falls back to
**simulation mode** — it generates realistic fake results so you can
demo the full UI flow without real browser automation.
