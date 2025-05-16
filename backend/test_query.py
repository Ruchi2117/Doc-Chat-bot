import requests
import json

def test_question(question: str):
    url = "http://localhost:8000/ask"
    headers = {"Content-Type": "application/json"}
    data = {
        "question": question,
        "use_cache": True
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    # Handle Server-Sent Events response
    for line in response.iter_lines():
        if line:
            # Remove 'data: ' prefix and parse JSON
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data = line[6:]  # Remove 'data: ' prefix
                if data == '[DONE]':
                    break
                try:
                    result = json.loads(data)
                    if 'error' in result:
                        print(f"Error: {result['error']}")
                    else:
                        print(f"Response: {result['chunk']}")
                        if result.get('metadata'):
                            print(f"Source: {result['metadata']}")
                except json.JSONDecodeError:
                    print(f"Could not parse: {data}")

# Test questions
questions = [
    "What are the primary colors?",
    "What happens when you mix red and yellow?",
    "What are warm colors associated with?",
    "Which colors are complementary to each other?"
]

print("Testing RAG system with sample questions...")
for question in questions:
    print(f"\nQuestion: {question}")
    test_question(question) 