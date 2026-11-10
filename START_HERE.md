# Kartiq: run it on your own computer

**Kartiq** is an online store built on MongoDB, with a FastAPI back end and a React front end. It runs on the real Olist e-commerce data, with live order tracking, personal offers and recommendations, and a 3-D "taste map" of the store's aisles.

This folder has everything needed to run it, including the real data in `data/raw`. (If `data/raw` has no CSV files, as in the smaller course-submission zip, download the dataset from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce and put its CSV files there.) The first time takes about 15 minutes. After that, starting it is one command.

## What you need

| | Where to get it |
|---|---|
| **Python 3.11, 3.12, 3.13 or 3.14** (3.13 is a safe choice; 3.15 is too new for one of the packages) | https://www.python.org/downloads/. On Windows, tick **"Add python.exe to PATH"** in the installer. |
| **MongoDB Community Server 7.0 or 8.0** | https://www.mongodb.com/try/download/community |
| A web browser | Chrome, Edge, Firefox or Safari |

You do **not** need Node.js: the website is already built (`frontend/dist`).

## Step 1: run MongoDB as a replica set (one time)

Kartiq uses MongoDB **transactions** (checkout) and **Change Streams** (live updates), and both need MongoDB to run as a replica set. One computer is enough. You only change one setting.

### Windows

1. Install MongoDB Community Server with the installer, and keep **"Install MongoD as a Service"** ticked.
2. Open **Notepad as administrator**: press Start, type `Notepad`, right-click it and choose **Run as administrator**.
3. In Notepad choose **File > Open**, set the file type to **All Files**, and open:
   `C:\Program Files\MongoDB\Server\8.0\bin\mongod.cfg`
   (use `7.0` in the path if you installed 7.0).
4. Find the line `#replication:` and replace it with these two lines (two spaces before `replSetName`), then save:
   ```yaml
   replication:
     replSetName: rs0
   ```
5. Open **Command Prompt as administrator** and restart MongoDB:
   ```bat
   net stop MongoDB
   net start MongoDB
   ```

### macOS (with Homebrew)

```bash
brew tap mongodb/brew
brew install mongodb-community
printf 'replication:\n  replSetName: rs0\n' >> "$(brew --prefix)/etc/mongod.conf"
brew services restart mongodb-community
```

### Linux (Ubuntu or Debian)

Install MongoDB with the official guide (https://www.mongodb.com/docs/manual/administration/install-on-linux/), then:

```bash
printf 'replication:\n  replSetName: rs0\n' | sudo tee -a /etc/mongod.conf
sudo systemctl restart mongod
```

### Any computer with Docker (instead of the above)

```bash
docker run -d --name kartiq-mongo -p 27017:27017 mongo:8 --replSet rs0
```

You do not need to run `rs.initiate()` yourself: the setup in step 2 does it.

## Step 2: set up Kartiq (one command, about 5 minutes)

Unzip the folder anywhere and open `retail-intelligence-platform`.

- **Windows:** double-click `scripts\setup_windows.bat`
- **macOS / Linux:** open a Terminal in the folder and run:
  ```bash
  bash scripts/setup_mac_linux.sh
  ```

The setup does the following:
1. Creates a Python environment (`venv`) and installs the packages. It picks Python 3.13, 3.12, 3.14 or 3.11 if one is installed.
2. Checks that MongoDB works, including a transaction and a Change Stream.
3. Loads the 99,441 real orders.
4. Generates the simulated shopping activity.
5. Trains the three models.
6. Creates the demo accounts.

It ends with **"Kartiq is ready."**

## Step 3: start the store

- **Windows:** double-click `scripts\start_app_windows.bat`
- **macOS / Linux:** run `bash scripts/start_app.sh`

Then open **http://localhost:8100**. Keep that window open while you use the store, and press **Ctrl+C** in it to stop. Next time you only need step 3, with MongoDB running.

## Logins to try

These are demo accounts made for this app, created by the setup. You can also sign up with any email.

| Who | Email | Password |
|---|---|---|
| Admin (the Operations area) | `admin@retail-intel.test` | `Admin#2026demo` |
| Lara, a loyal **Plus** member | `loyal@retail-intel.test` | `Shopper#2026demo` |
| Bruno, a big spender | `bigspender@retail-intel.test` | `Shopper#2026demo` |
| Alice, an at-risk customer | `atrisk@retail-intel.test` | `Shopper#2026demo` |

Payments are simulated, so no real money is involved. Test card `4242 4242 4242 4242` (any future expiry, any CVV) is approved, and `4000 0000 0000 0002` is always declined.

## Things to try (5 minutes)

1. On the home page, watch the taste map: each dot is an aisle, and pulses travel to the aisles the same shoppers buy from. Drag it, or tap an aisle.
2. Open **How Kartiq works** in the top bar and scroll.
3. Sign in as Lara. Add something to the cart (watch it fly into the cart icon), then check out with the test card. The order page moves to *Shipped* and then *Delivered* by itself, in 20-second steps.
4. Sign in as the admin, open **Operations** and press **Start simulated traffic** to see live activity.

## If something goes wrong

| What you see | What to do |
|---|---|
| `Could not reach MongoDB` | MongoDB is not running. **Windows** (admin Command Prompt): `net start MongoDB`. **macOS:** `brew services start mongodb-community`. **Linux:** `sudo systemctl start mongod`. |
| `MongoDB is running, but not as a replica set` | Step 1's two lines are missing or mis-indented, or MongoDB was not restarted after adding them. |
| `'python' is not recognized` (Windows) | Reinstall Python and tick "Add python.exe to PATH". |
| Installing the packages fails (often while building pandas or scikit-learn) | Use Python 3.12 or 3.13. Delete the `venv` folder, then on macOS/Linux run `PYTHON=python3.12 bash scripts/setup_mac_linux.sh`. On Windows, first run `py -3.12 -m venv venv`, then `scripts\setup_windows.bat`. |
| `address already in use` / port 8100 is busy | Use another port. macOS/Linux: `PORT=8200 bash scripts/start_app.sh`. Windows Command Prompt: `set PORT=8200`, then `scripts\start_app_windows.bat`. Open http://localhost:8200. |
| MongoDB is on another port, another computer or Atlas | Set `MONGO_URI` before steps 2 and 3, e.g. `export MONGO_URI="mongodb://localhost:27018"` (macOS/Linux) or `set MONGO_URI=mongodb://localhost:27018` (Windows). |
| The store opens but shows no products | Step 2 did not finish. Run it again; it is safe to repeat. |

To re-check Python, the data and MongoDB without loading anything, run `venv/bin/python scripts/setup_kartiq.py --check` (Windows: `venv\Scripts\python scripts\setup_kartiq.py --check`).

## What is in the folder

| Path | What it is |
|---|---|
| `README.md` | What the project does and how, in detail |
| `docs/report.md`, `docs/Retail_Intelligence_Report.docx` | The written report, with screenshots |
| `backend/` | FastAPI back end (API, transactions, Change Stream worker) |
| `frontend/` | React front end (`dist/` is the built website) |
| `pipelines/`, `ml/` | The MongoDB aggregation pipelines and the three models |
| `data/` | Data loaders, and the real Olist data in `data/raw` (see `data/raw/ABOUT_THIS_DATA.txt`) |
| `simulator/` | Generates the simulated shopping activity |
| `notebooks/ml_analysis.ipynb` | The analysis behind the models |
| `tests/`, `backend/tests/` | Automated tests: `venv/bin/python -m pytest` (they use a separate `retail_intel_test` database) |

The data is the Brazilian E-Commerce Public Dataset by Olist (Kaggle), licensed CC BY-NC-SA 4.0, for non-commercial, educational use. Prices are shown in rupees at a fixed rate of ₹17.80 per R$1.
