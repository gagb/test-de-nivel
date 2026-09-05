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
- If you change questions in `test-data.json`, run `python3 build.py` in the
  Bash console to regenerate `index.html`, then click **Reload**.
- Back up grades any time by downloading the CSV, or the `results.db` file
  from the Files tab.
