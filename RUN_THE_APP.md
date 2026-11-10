# Run the store (FastAPI + React + MongoDB)

Running it on another computer (Windows, macOS or Linux)? Follow `START_HERE.md` instead: two scripts do everything.

1. Start MongoDB as a replica set. Transactions and Change Streams need one; this Mac is already configured (`rs0`).

   ```bash
   brew services start mongodb-community@7.0
   ```

2. Load the data and train the models (one time, about 2 minutes, run from this folder):

   ```bash
   venv/bin/python data/load_olist_data.py --raw-dir data/raw
   venv/bin/python schema/create_indexes.py
   venv/bin/python simulator/event_simulator.py --mode batch --n-customers 1500 --n-sessions 6000 --seed 42
   venv/bin/python ml/run_all.py
   ```

3. Build the front end once, then start the app:

   ```bash
   (cd frontend && npm install && npm run build)
   ./scripts/start_app.sh
   ```

   Open http://localhost:8100. The API docs are at http://localhost:8100/docs.

The admin account and three demo shoppers are created automatically on start-up. They are linked to real Olist customers by segment. Their test logins are in `backend/app/seed.py`.

Try this:
- Sign up, search, add to cart, and pay with test card `4242 4242 4242 4242`. Watch the order go processing → shipped → delivered live, over about 40 seconds.
- Pay with `4000 0000 0000 0002` to see a declined payment.
- Log in as the admin and open **Operations**. Start the simulated traffic to see live events, alerts and orders held for review.
