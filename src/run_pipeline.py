"""Run the cleaning and EDA stages in the correct dependency order."""

from clean_311_data import main as clean_data
from run_eda import main as run_eda


if __name__ == "__main__":
    # Why: EDA depends on the cleaned dataset, so the orchestrator always runs
    # cleaning first and eliminates accidental analysis of stale processed data.
    clean_data()
    run_eda()
    print("Pipeline complete: cleaned data and EDA outputs are ready.")
