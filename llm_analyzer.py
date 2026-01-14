"""
LLM Analyzer - Compare GPT-5-nano vs Claude Haiku 4.5
For analyzing user events and extracting insights
"""

import os
import json
import time
from dotenv import load_dotenv
from openai import OpenAI
import boto3

load_dotenv()


class GPT5NanoAnalyzer:
    """OpenAI GPT-5-nano analyzer"""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = "gpt-5-nano"

    def analyze(self, prompt, events_json):
        """Analyze events using GPT-5-nano"""
        start_time = time.time()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Events data:\n{events_json}"}
            ],
            # Note: gpt-5-nano only supports temperature=1 (default)
        )

        elapsed = time.time() - start_time

        return {
            'model': self.model,
            'response': response.choices[0].message.content,
            'elapsed_seconds': elapsed,
            'input_tokens': response.usage.prompt_tokens,
            'output_tokens': response.usage.completion_tokens,
        }


class HaikuAnalyzer:
    """AWS Bedrock Claude Haiku 4.5 analyzer"""

    def __init__(self):
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        )
        self.model_id = os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-haiku-20241022-v1:0')

    def analyze(self, prompt, events_json):
        """Analyze events using Claude Haiku 4.5 via Bedrock"""
        start_time = time.time()

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0.3,
            "system": prompt,
            "messages": [
                {"role": "user", "content": f"Events data:\n{events_json}"}
            ]
        })

        response = self.client.invoke_model(
            modelId=self.model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )

        elapsed = time.time() - start_time
        result = json.loads(response['body'].read())

        return {
            'model': self.model_id,
            'response': result['content'][0]['text'],
            'elapsed_seconds': elapsed,
            'input_tokens': result['usage']['input_tokens'],
            'output_tokens': result['usage']['output_tokens'],
        }


def compare_models(events, prompt):
    """Run same analysis on both models and compare results"""
    events_json = json.dumps(events, indent=2, default=str)

    results = {}

    # GPT-5-nano
    print("Running GPT-5-nano analysis...")
    try:
        gpt_analyzer = GPT5NanoAnalyzer()
        results['gpt5_nano'] = gpt_analyzer.analyze(prompt, events_json)
        print(f"  Completed in {results['gpt5_nano']['elapsed_seconds']:.2f}s")
    except Exception as e:
        print(f"  GPT-5-nano error: {e}")
        results['gpt5_nano'] = {'error': str(e)}

    # Haiku 4.5
    print("Running Haiku 4.5 analysis...")
    try:
        haiku_analyzer = HaikuAnalyzer()
        results['haiku_4_5'] = haiku_analyzer.analyze(prompt, events_json)
        print(f"  Completed in {results['haiku_4_5']['elapsed_seconds']:.2f}s")
    except Exception as e:
        print(f"  Haiku 4.5 error: {e}")
        results['haiku_4_5'] = {'error': str(e)}

    return results


# Analysis prompts for different tasks
PROMPTS = {
    'classify_events': """You are an expert at analyzing user behavior events.
Classify each event by:
1. Event category (content consumption, physical activity, social, transaction, etc.)
2. Interest signal strength (high/medium/low) - how much does this reveal about user interests?
3. Key topics or themes

Return a structured analysis.""",

    'extract_interests': """You are a user insights analyst.
From these events, identify:
1. Primary interests (topics the user engages with most)
2. Secondary interests (occasional engagement)
3. Behavioral patterns (time of day, frequency, etc.)
4. Interest evolution (if timestamps show changes over time)

Be specific and cite evidence from the events.""",

    'user_journey': """You are a user journey analyst.
Analyze these events to tell the story of this user:
1. What brought them to the platform?
2. How has their engagement evolved?
3. What are their core motivations?
4. What might they want next?

Create a narrative user journey based on the evidence.""",
}


if __name__ == "__main__":
    # Load sample events
    try:
        with open('sample_events.json', 'r') as f:
            events = json.load(f)
    except FileNotFoundError:
        print("Run kafka_consumer.py first to fetch sample events")
        exit(1)

    # Use all events or specify via command line
    import sys
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else len(events)
    sample_size = min(sample_size, len(events))
    sample_events = events[:sample_size]

    print(f"\nComparing models on {sample_size} events...")
    print("="*50)

    # Run classification comparison
    results = compare_models(sample_events, PROMPTS['classify_events'])

    # Print results
    print("\n" + "="*50)
    print("RESULTS COMPARISON")
    print("="*50)

    for model_name, result in results.items():
        print(f"\n--- {model_name.upper()} ---")
        if 'error' in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Time: {result['elapsed_seconds']:.2f}s")
            print(f"Tokens: {result['input_tokens']} in / {result['output_tokens']} out")
            print(f"Response preview:\n{result['response'][:1000]}...")

    # Save full results
    with open('model_comparison.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\nFull results saved to model_comparison.json")
