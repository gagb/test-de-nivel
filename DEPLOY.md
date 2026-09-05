# Deploying the placement test

Two supported ways to run it:

- **[Serve over a Cloudflare tunnel](#serve-over-a-cloudflare-tunnel)** —
  simplest and free; the app runs on the teacher's laptop for a class session.
- **[Deploy to PythonAnywhere](#deploying-to-pythonanywhere-free-tier)** —
  always-on hosting with a persistent database.

---

# Serve over a Cloudflare tunnel

Best for running the test during a class. The app runs on your laptop and
Cloudflare gives it a temporary public URL. Data stays in `results.db` on your
machine. The laptop must stay awake, online, and running the app for the whole
test.

## One-time setup

Install `cloudflared` once. Pick your system:

**Mac with Apple Silicon (M1/M2/M3/M4)** — in Terminal, no sudo needed:

```bash
curl -sSL -o /tmp/cloudflared.tgz \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz
mkdir -p ~/.local/bin && tar -xzf /tmp/cloudflared.tgz -C ~/.local/bin
chmod +x ~/.local/bin/cloudflared
~/.local/bin/cloudflared --version        # confirm it works
```

**Mac with Intel** — same, with `amd64` in the file name:

```bash
curl -sSL -o /tmp/cloudflared.tgz \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz
mkdir -p ~/.local/bin && tar -xzf /tmp/cloudflared.tgz -C ~/.local/bin
chmod +x ~/.local/bin/cloudflared
~/.local/bin/cloudflared --version
```

Not sure which Mac you have? Apple menu → *About This Mac*. "Chip: Apple …"
is Apple Silicon; "Processor: Intel …" is Intel. If you use Homebrew, either
Mac can instead run `brew install cloudflared`.

`serve.sh` looks in `~/.local/bin` automatically, so you don't need to change
your PATH.

**Windows** — open PowerShell and run:

```powershell
winget install --id Cloudflare.cloudflared
```

Close and reopen PowerShell, then `cloudflared --version` to confirm. If
`winget` isn't available, download `cloudflared-windows-amd64.exe` from
<https://github.com/cloudflare/cloudflared/releases/latest>, rename it to
`cloudflared.exe`, and put it in the project folder.

**Linux (Debian/Ubuntu)**:

```bash
curl -sSL -o /tmp/cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i /tmp/cloudflared.deb
cloudflared --version
```

Then install the Python dependency once (all systems). On Windows use `pip`
and `python` instead of `pip3` and `python3`:

```bash
pip3 install --user -r requirements.txt
```

## Each time you run the test

**Mac or Linux** — from the project folder:

```bash
ACCESS_CODE=hola2026 TEACHER_PASSWORD=yourpassword ./serve.sh
```

The script starts the server and prints a public URL like
`https://something-random.trycloudflare.com`. Share that URL **and the access
code** with students. The teacher console is that URL with `/teacher` added;
log in with any username and the password you set. Press **Ctrl-C** to stop the
server and close the tunnel.

**Windows** — the start script is for Mac/Linux, so run the two parts by hand.
Open PowerShell in the project folder and start the server:

```powershell
$env:ACCESS_CODE = "hola2026"
$env:TEACHER_PASSWORD = "yourpassword"
python app.py
```

Leave that window open. Open a **second** PowerShell window and start the
tunnel:

```powershell
cloudflared tunnel --url http://127.0.0.1:5000
```

(If you put `cloudflared.exe` in the project folder instead of installing it,
use `.\cloudflared.exe` in that command.) The public URL appears in this second
window after a few seconds. To stop, press **Ctrl-C** in both windows.

Notes:
- The `trycloudflare.com` URL is new every run and stops working once you press
  Ctrl-C. Start the script before class and keep it running until everyone is
  done.
- The new URL can take 10–20 seconds to start resolving. If a browser says it
  can't find the site right after launch, wait a moment and reload. Don't
  open it on the teacher's own laptop in the first seconds: macOS may cache
  the "not found" answer for a few minutes.
- Grades are saved to `results.db` on your laptop and stay there after you
  stop. Download them any time from the teacher console's **Download CSV**.

---

# Deploying to PythonAnywhere (free tier)

This hosts the placement test at a public URL like
`https://USERNAME.pythonanywhere.com/`, with the results database stored
persistently in your account.

You do these steps once, in your browser, logged into your own
PythonAnywhere account.

## 1. Create a free account

Sign up at <https://www.pythonanywhere.com/> and choose the free
"Beginner" plan.

## 2. Get the project onto PythonAnywhere

Open a **Bash console** from the PythonAnywhere Dashboard, then either:

**Option A — from GitHub** (if you push this repo to GitHub):

```bash
git clone https://github.com/YOURNAME/YOURREPO.git fernando
```

**Option B — upload a zip:** on your Mac, zip the project folder, use the
**Files** tab on PythonAnywhere to upload the zip into your home directory,
then in the Bash console:

```bash
unzip fernando.zip -d fernando
```

Either way you should end up with the files in `/home/USERNAME/fernando`.

## 3. Install Flask

In the Bash console:

```bash
pip3 install --user Flask
```

## 4. Create the web app

1. Go to the **Web** tab, click **Add a new web app**.
2. Choose **Manual configuration** (not the "Flask" quickstart).
3. Pick the latest Python 3 version offered.

## 5. Point it at this project

On the **Web** tab, find the **WSGI configuration file** link (something like
`/var/www/USERNAME_pythonanywhere_com_wsgi.py`) and click it. Delete
everything in that file and paste the contents of `pythonanywhere_wsgi.py`
from this project. Then edit two things in it:

- Set `USERNAME` to your PythonAnywhere username.
- Set the teacher password on the `TEACHER_PASSWORD` line.
- Set the student access code on the `ACCESS_CODE` line.

Save the file.

## 6. Reload and test

Click the green **Reload** button on the Web tab. Then:

- Student test: `https://USERNAME.pythonanywhere.com/`
- Teacher console: `https://USERNAME.pythonanywhere.com/teacher`
  (any username, the password you set in step 5). The **Download CSV** button
  there opens directly in Excel.

## Notes

- The results database (`results.db`) lives in the project folder on
  PythonAnywhere's persistent disk, so grades survive reloads and restarts.
- Free accounts must click **Reload** on the Web tab once every three months
  to keep the app running; PythonAnywhere emails a reminder.
- If you change questions in `test-data.json`, click **Reload** on the Web
  tab; the server reads the file at startup.
- Back up grades any time by downloading the CSV, or the `results.db` file
  from the Files tab.
