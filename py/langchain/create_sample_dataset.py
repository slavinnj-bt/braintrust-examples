"""
Create a sample dataset for testing the generic chatbot eval

This script loads questions from travel.json and creates a dataset.
Customize this for your specific use case.
"""

from braintrust import init_dataset
from dotenv import load_dotenv
import os
import json

load_dotenv()

# Load travel questions from travel.json
def load_travel_data():
    """Load questions from travel.json"""
    with open('travel.json', 'r') as f:
        data = json.load(f)

    # Extract just the input field from each record
    sample_data = [{"input": item["input"]} for item in data]
    return sample_data

sample_data = load_travel_data()

def create_dataset(project_name="Generic Chatbot Eval", dataset_name="ChatbotQuestions"):
    """Create a sample dataset in Braintrust"""

    # Initialize the dataset
    dataset = init_dataset(
        project_name,
        {
            "dataset": dataset_name,
            "data": sample_data
        }
    )

    print(f"✓ Created dataset '{dataset_name}' in project '{project_name}'")
    print(f"  Added {len(sample_data)} sample questions")
    print(f"\nNext steps:")
    print(f"1. Run: braintrust eval remote_chatbot_eval.py --dev")
    print(f"2. Open Braintrust playground")
    print(f"3. Configure your eval parameters")

    return dataset


if __name__ == "__main__":
    # Get project name from environment or use default
    project_name = os.environ.get("BRAINTRUST_PROJECT", "Generic Chatbot Eval")

    create_dataset(project_name)
