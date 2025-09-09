# Chicago Housing Analysis Dashboard

This project is a comprehensive tool for analyzing real estate properties in Chicago. It aggregates data from multiple sources, including Redfin listings, Google Maps APIs (for commute times and nearby amenities), and public Chicago datasets (for crime, demographics, and socioeconomic indicators).

The data is processed into a single, enriched dataset, and a weighted `OVERALL_SCORE` is calculated for each property based on user-defined preferences. The results are then served through a Flask-based web dashboard for interactive filtering, sorting, and visualization on a map.

<img width="1888" height="982" alt="image" src="https://github.com/user-attachments/assets/43c416f5-f7c6-443e-8846-a8242e4586f7" />


## Features

- **Data Aggregation**: Combines property data with commute times, nearby amenities, crime statistics, and demographic information.
- **Custom Scoring**: Calculates a weighted `OVERALL_SCORE` based on commute, safety, amenities, and value.
- **API Caching**: Uses a local SQLite database to cache Google Maps API calls, saving time and money on subsequent runs.
- **Interactive Dashboard**: A web interface built with Flask and Tailwind CSS to browse, filter, and view property details.
- **Map Visualization**: Displays properties on a Leaflet map with overlays for CTA train lines.

--- 

## Setup and Installation

Follow these steps to get the project running on your local machine.

### 1. Prerequisites
- Python 3.8 or newer
- Git

### 2. Clone the Repository

```bash
git clone <your-repository-url>
cd housing_app
```

### 3. Install Dependencies

It's recommended to use a virtual environment to manage dependencies.

```bash
# Create a virtual environment (e.g., venv)
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install the required packages
pip install -r requirements.txt
```

### 4. Set Up Google API Key

This project requires a Google Maps API key with the **Directions API**, **Places API**, and **Distance Matrix API** enabled.

1.  Create a folder named `delete` in the project root.
2.  Inside the `delete` folder, create a file named `input.txt`.
3.  Paste your Google Maps API key into this file and save it. The project is configured via `.gitignore` to never commit this folder.

### 5. Add Data Files

Place your raw data CSV files into the `data_sets/` directory. The script expects the following files:

- `RedFin_raw_data.csv`
- `socioeconomic_indicators.csv`
- `languages_spoken.csv`
- `Crimes_-_202103.csv`
- `Affordable_Rental_Housing_Developments.csv`

---

## How to Run

The project has two main components: the data processing script and the web application.

### 1. Run the Data Processing Script

Execute `main_data.py` from your terminal to process the raw data and generate the `output/final_data.csv` file. This script can take a while to run, especially the first time, as it makes numerous API calls.

```bash
python main_data.py
```

You can use command-line arguments to customize the run:
- `--skip-commute`: Skips the slow commute time calculations.
- `--skip-places`: Skips the slow nearby amenities calculations.
- `--mls 12345,67890`: Only process specific properties by their MLS ID.
- `--w-commute 0.5 --w-crime 0.2`: Adjust the weights for the `OVERALL_SCORE` calculation.

Run `python main_data.py --help` for a full list of options.

### 2. Run the Web Application

Once the `output/final_data.csv` file has been generated, you can start the Flask web server.

```bash
python app.py
```

The application will be accessible at `http://localhost:5000` and on your local network.

---
