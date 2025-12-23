<img width="1539" height="1316" alt="image" src="https://github.com/user-attachments/assets/2e58d209-6dd0-4b22-9ec2-2f4ca2760a99" />


# SaveSmart – Work-Hour Based Purchase Decision Application

SaveSmart is a personal finance MVP built with Streamlit that helps users make
more rational purchasing decisions by converting product prices into the
amount of working time required to earn that money.

Instead of focusing only on monetary cost, SaveSmart reframes spending decisions
in terms of time, encouraging users to think carefully before making purchases.

---

## Motivation

Many personal finance tools focus on tracking expenses after money has already
been spent. SaveSmart addresses an earlier and often overlooked stage of the
decision-making process:

**Should I buy this at all?**

By translating prices into required working hours and income impact,
SaveSmart helps users evaluate whether a purchase is truly worth their time and effort.

---

## Core Concept

SaveSmart is based on a simple but powerful idea:

> Money is earned with time.  
> Every purchase represents a portion of your working life.

The application converts each purchase into:
- Required working hours
- Equivalent working days
- Percentage of monthly income

This approach makes the cost of an item more tangible and easier to evaluate.

---

## Key Features

### Income & Work Profile
- Supports daily, weekly, monthly, or yearly income
- Configurable working hours per day
- Configurable working days per week and per month
- Optional fixed monthly expenses

### Purchase Goals
- Add items with price, category, and necessity level (1–5)
- Optional target purchase date
- Visual representation using emoji or uploaded images
- Goal status management (active, snoozed, achieved, deleted)

### Financial Calculations
- Hourly income rate estimation
- Required working hours per item
- Equivalent working days
- Monthly income percentage impact
- Priority scoring based on necessity and effort required

### Savings Management
- Manual savings deposits per goal
- Real-time progress tracking
- Remaining amount calculation
- Visual progress bar per item

### Planning & Reminders
- Savings plan estimation based on target date
- Weekly and monthly saving requirements
- In-app reminders
- Snooze and disable reminder options

### Data Export
- Export purchase goals to CSV
- Export savings records to CSV
- Enables external analysis or backup

---

## Application Architecture

SaveSmart is intentionally designed as a local-first MVP.

- Single-user system (user_id = 1)
- No authentication or backend server
- SQLite used for persistence
- Streamlit used for UI and interaction

This design prioritizes clarity, maintainability, and rapid iteration over production scale.

---

## Technology Stack

- Python
- Streamlit
- SQLite
- Pandas

---

## Project Structure


---

## How to Run the Application

Install dependencies:

```bash
pip install streamlit pandas
Run the application using Streamlit:

streamlit run money1.py


Then open the browser at:

http://localhost:8501


Important notes:

Do not run using python money1.py

The application is intended for local use

Project Status

MVP complete

Fully functional for local usage

Designed for learning, experimentation, and portfolio demonstration

This project is not intended to be a production-scale financial system.
Its primary purpose is to demonstrate reasoning, data handling,
and decision-support logic.
