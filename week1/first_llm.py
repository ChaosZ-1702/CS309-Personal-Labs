from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), base_url = os.getenv("BASE_URL"))

def stream_response(prompt): 
    """Demonstrate streaming response""" 
    stream = client.chat.completions.create( 
        model="gemini-2.5-flash", 
        messages=[{"role": "user", "content": prompt}], 
        stream=True 
    ) 
    print("Assistant: ", end="")
    collected_messages = []
    for chunk in stream:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            collected_messages.append(content)
            print(content, end="", flush=True)
    print()
    # Newline 
    return "".join(collected_messages)

# Test streaming output 
stream_response("Introduce quantum computing in 100 words") 