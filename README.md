# DSH-CTM-ETM Pipeline

This app takes plant data, turns it into Excel files, and sends energy
scenario data to CTM (and optionally ETM). It's all run through a simple
web page (Streamlit) that opens in your browser.

## What you need before starting

- A computer with Python already installed (ask a colleague if you're not
  sure — you can check by opening a terminal and typing `python3 --version`)
- The project files (this folder)


# Download the project files

### Option A: Using ```git clone``` - **RECOMMENDED**

This requires having a git account and configuring the git credentials on your computer.

1. Check if git is installed on your computer (type git in the search bar). If missing, request it / download it / install it.
2. Create a git account.
3. Click the green '<> Code' button, select HTTPS -> copy URL
4. Open GIT GUI and select clone project. Follow instructions. OR open a command window, navigate to the location where you want to store the project ('C:/User/Projects/..' for example) and run the following command:
``` git clone <copied URL> ```

* in order to navigate to a certain folder location in a command window, run the command: ```cd path/to/desired/location```

* in case updates are made to the code on git, you can automatically fetch them by running the command ```git pull origin main```

**UPSIDE**: Easily update your local copy of the code if there are changes made to the git repository.

**DOWNSIDE**: A bit more work and setup needed.

### Option B: Using direct download

1. Click the green '<> Code' button and select 'Download ZIP'
2. Unarchive the zip file where you want to store the project locally.

**UPSIDE**: Quick and simple. 

**DOWNSIDE**: Code updates cannot be automatically fetched from github.

# Create a python environment and run
## Step 1: Open a terminal

- **Mac**: open the "Terminal" app
- **Windows**: open "Command Prompt" or "PowerShell"

Then move into the project folder. This is where you unarchived / cloned the repository. For example:

```
cd path/to/epn-ma-master
```

(Replace `path/to/epn-ma-master` with wherever you saved the project.)

## Step 2: Install the required packages

You only need to do this once (or again later if the project changes).
Pick **one** of the two options below — either is fine.

### Option A: using `pip` (the standard way)

Create a virtual environment (venv). This creates a copy of your python interpreter specifically used just for this project. Second line of code activates the environment (meaning you will be running python commands with the copy version).

```
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, use this instead for the second line:
```
.venv\Scripts\activate
```

Then install everything the app needs:

```
pip install -r requirements.txt
```

### Option B: using `uv` (a faster, newer tool)

If you don't have `uv` yet, install it first (you will probably need to request it):

Install python with uv
```
uv python install 3.12.4
```

Then, from the project folder:

```
uv venv -- python 3.12.4
uv init
uv sync
```

Install the requirements:

```uv add -r requirements.txt```

## Step 3: Run the app

Pick the option that matches what you used in Step 2.

**If you used pip:**
```
python -m streamlit run src/streamlit_app.py
```

**If you used uv:**
```
uv run python -m streamlit run src/streamlit_app.py
```

A browser window should open automatically. If it doesn't, look in the
terminal for a line like `Local URL: http://localhost:8501` and open that
link yourself.

## Step 4: Using the app

The app has a few tabs at the top:

1. **DSH Input & Output** — upload your data files here, and the app
   generates an Excel file for each plant.
2. **CTM/ETM Workflow** — upload the Excel files from Step 1, plus a
   mapping file, and send the data to CTM. You can also connect it to ETM
   afterward.
3. **Visualizations** — once you've loaded plant data, explore charts
   showing emissions and energy use over time.

There's also a sidebar (on the left) where you can download summary Excel
files once you've loaded your data.

## Stopping the app

Go back to the terminal window where the app is running and press
`Ctrl + C`.

## If something goes wrong

- Make sure you're in the right folder (Step 1) before running commands.
- Make sure you completed Step 2 before Step 3 — the app won't run without
  its packages installed.
- If you closed the terminal, just reopen it, go back to the project folder,
  and repeat Step 3 (you don't need to redo Step 2 unless the project has
  changed).
