"""Field Shift launcher: one command to set up (optional Earth Engine) and start the app.

AI-assisted: generated with an AI coding assistant (Claude) and reviewed by the team.

    python run.py             first run: installs missing packages, offers the Earth Engine setup,
                              starts the server and opens the browser
    python run.py --setup     (re)configure Earth Engine, then start
    python run.py --no-ee     start straight away with the no-login sources only
    python run.py --port 8001

Without Earth Engine the app already works: NASA POWER climate, USDA SSURGO soil and USDA
CropScape crop history need no account. Earth Engine adds NDVI (Landsat), SMAP soil moisture and
the 30 m slope / risk zones. Its setup needs, once: a Google sign-in in the browser and a Cloud
project registered for (free, noncommercial) Earth Engine use. This script asks for everything at
the start and writes EE_PROJECT_ID into .env for you.
"""
import argparse
import re
import secrets
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV, ENV_EXAMPLE = ROOT / ".env", ROOT / ".env.example"
REGISTER_URL = "https://code.earthengine.google.com/register"


# ---------------------------------------------------------------------------------------------
# Small helpers
def say(msg=""):
    print(msg, flush=True)


def ask(question, default=""):
    """input() with a default; non-interactive runs (no terminal) take the default."""
    if not sys.stdin.isatty():
        return default
    suffix = f" [{default}]" if default else ""
    ans = input(f"{question}{suffix}: ").strip()
    return ans or default


def yes(question, default=True):
    ans = ask(f"{question} ({'Y/n' if default else 'y/N'})", "y" if default else "n").lower()
    return ans.startswith("y") or ans.startswith("s")        # accepts "sí" too


def read_env():
    if not ENV.exists():
        return {}
    out = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def set_env(key, value):
    """Write KEY=value in .env, keeping every other line (creates .env from .env.example)."""
    ensure_env()
    lines = ENV.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*{key}\s*=", line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_env():
    if not ENV.exists():
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, ENV)
        else:
            ENV.write_text("EE_PROJECT_ID=\n", encoding="utf-8")
        say("Created .env from .env.example.")


def ensure_packages():
    missing = []
    for mod in ("fastapi", "uvicorn", "pandas", "numpy", "requests", "shapely", "dotenv", "ee"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return
    say(f"Missing Python packages: {', '.join(missing)}.")
    if yes("Install them now from requirements.txt?"):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
    else:
        sys.exit("Run: python -m pip install -r requirements.txt")


# ---------------------------------------------------------------------------------------------
# Earth Engine
def ee_works(project):
    """(True, '') if Earth Engine answers with this project, else (False, short reason)."""
    import ee
    try:
        ee.Initialize(project=project)
        ee.Number(1).getInfo()
        return True, ""
    except Exception as e:                      # never print tokens or paths
        msg = str(e).splitlines()[0][:200] if str(e) else type(e).__name__
        return False, msg


def have_credentials():
    from ee import oauth
    try:
        return bool(oauth.get_credentials_arguments().get("refresh_token"))
    except OSError:
        return False


def sign_in():
    import ee
    say("\nStep 1/3 · Google sign-in. A browser tab opens: sign in with the Google account you will use for "
        "Earth Engine and press 'Allow'.")
    try:
        ee.Authenticate(auth_mode="localhost")
    except Exception:
        say("The automatic sign-in did not work; switching to copy-and-paste mode.")
        ee.Authenticate(auth_mode="notebook")


def candidate_projects():
    """Projects we can try without asking: the one stored in the EE credentials, then `gcloud projects list`.

    (Google does not let the Earth Engine sign-in list or create Cloud projects: those calls are billed to
    the Earth Engine client, which has no Resource Manager API. gcloud, if installed, can.)
    """
    from ee import oauth
    out = []
    try:
        stored = oauth.get_credentials_arguments().get("quota_project_id")
    except OSError:
        stored = None
    for p in (stored, oauth.get_appdefault_project()):
        if p and p not in out:
            out.append(p)
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud:
        try:
            res = subprocess.run([gcloud, "projects", "list", "--format=value(projectId)"], capture_output=True,
                                 text=True, timeout=60)
            out += [p for p in res.stdout.split() if p and p not in out]
        except (OSError, subprocess.SubprocessError):
            pass
    return out


def new_project_id():
    say("\nCreate a Google Cloud project (free; no billing account needed for noncommercial Earth Engine).")
    say("   A browser tab opens at https://console.cloud.google.com/projectcreate")
    suggestion = f"field-shift-{secrets.token_hex(3)}"
    say(f"   Type a project name, e.g. {suggestion}, press 'Create', then copy its Project ID.")
    webbrowser.open("https://console.cloud.google.com/projectcreate")
    return ask("Project ID of the new project")


def register(pid):
    say(f"\nStep 3/3 · Register project '{pid}' for free noncommercial Earth Engine use (Google asks this once; "
        "it also enables the Earth Engine API on the project).")
    say(f"   A browser tab opens at {REGISTER_URL}")
    say("   Choose 'Use with a Cloud project' → 'Unpaid usage' → your project type (e.g. 'Academia & Research'"
        " or 'No affiliation'), then 'Choose an existing Google Cloud Project' → " + pid + " → Confirm.")
    webbrowser.open(REGISTER_URL)
    for attempt in range(3):
        ask("Press Enter when the registration page says you are done")
        ok, why = ee_works(pid)
        if ok:
            return True
        say(f"Earth Engine does not answer for '{pid}' yet ({why}). Registration can take a minute.")
    return False


def setup_ee():
    import ee  # noqa: F401  (checks the package is installed)
    say("\n=== Earth Engine setup (optional, about 2 minutes) ===")
    current = read_env().get("EE_PROJECT_ID")
    if current:
        ok, why = ee_works(current)
        if ok:
            say(f"Earth Engine already works with project '{current}'. Nothing to do.")
            return True
        say(f"EE_PROJECT_ID='{current}' does not work ({why}). Let's fix it.")
    if not have_credentials():
        sign_in()
    else:
        say("Step 1/3 · Google sign-in: already done on this computer.")

    say("\nStep 2/3 · Cloud project. Looking for a project that already works with Earth Engine …")
    projects = candidate_projects()
    working = [p for p in projects[:15] if ee_works(p)[0]]
    pid = None
    if working:
        for i, p in enumerate(working, 1):
            say(f"   {i}. {p}")
        choice = ask("Use which one? (number)", "1")
        pid = working[int(choice) - 1] if choice.isdigit() and 0 < int(choice) <= len(working) else working[0]
    else:
        if projects:
            say("   Found these projects, none registered for Earth Engine yet: " + ", ".join(projects[:15]))
        pid = ask("Type the ID of the Cloud project to use (Enter = create a new one)")
        pid = pid or new_project_id()
        if not pid:
            say("No project given: Earth Engine stays off. Run `python run.py --setup` any time.")
            return False
        if not ee_works(pid)[0] and not register(pid):
            say("Earth Engine is still not answering. Saved the project anyway; run `python run.py --setup` "
                "again in a few minutes.")
            set_env("EE_PROJECT_ID", pid)
            return False
    set_env("EE_PROJECT_ID", pid)
    say(f"\nDone: EE_PROJECT_ID={pid} saved in .env. NDVI, SMAP and slope are now on.")
    return True


# ---------------------------------------------------------------------------------------------
def start_server(port):
    import requests
    url = f"http://127.0.0.1:{port}/"
    say(f"\nStarting Field Shift at {url}  (Ctrl+C to stop)")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.api:app", "--host", "127.0.0.1",
                             "--port", str(port)], cwd=ROOT)
    for _ in range(60):
        try:
            if requests.get(f"{url}api/health", timeout=1).ok:
                webbrowser.open(url)
                break
        except requests.RequestException:
            time.sleep(0.5)
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()


def main():
    ap = argparse.ArgumentParser(description="Set up and start Field Shift.")
    ap.add_argument("--setup", action="store_true", help="(re)configure Earth Engine before starting")
    ap.add_argument("--no-ee", action="store_true", help="do not ask about Earth Engine")
    ap.add_argument("--no-start", action="store_true", help="only set up, do not start the server")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    ensure_env()
    ensure_packages()
    if a.setup:
        setup_ee()
    elif not a.no_ee and not read_env().get("EE_PROJECT_ID"):
        say("Earth Engine is not configured. The app works without it (climate, soil and crop history need no "
            "login); Earth Engine adds NDVI, SMAP soil moisture and the 30 m slope maps.")
        if yes("Set up Earth Engine now?", default=False):
            setup_ee()
        else:
            say("OK. You can run `python run.py --setup` any time.")
    if not a.no_start:
        start_server(a.port)


if __name__ == "__main__":
    main()
