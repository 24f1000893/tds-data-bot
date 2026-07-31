#!/usr/bin/env python3
import os
import sys
import json
import time
import re
import urllib.request
import urllib.parse
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
import subprocess
import tempfile
import ssl
import traceback

try:
    ssl_context = ssl._create_unverified_context()
except AttributeError:
    ssl_context = None

# Load dotenv if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PORT = int(os.environ.get("PORT", 8000))
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PUBLIC_URL = os.environ.get("PUBLIC_URL")  # e.g., https://yourdomain.serveo.net

if not BOT_TOKEN:
    print("Warning: BOT_TOKEN environment variable not set. Please set it in your environment or .env file.")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# In-memory history: chat_id -> list of {"role": "user"|"assistant", "text": "..."}
chat_histories = {}
history_lock = threading.Lock()

# Web server to serve run.jsonl
class LogHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/run.jsonl':
            self.send_response(200)
            self.send_header('Content-type', 'application/x-jsonlines')
            # Add CORS headers for flexibility
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                with open('run.jsonl', 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(b"")
        else:
            self.send_error(404, "File not found")

    def log_message(self, format, *args):
        # Silence default log messages to stdout
        pass

def run_server():
    server = HTTPServer(('0.0.0.0', PORT), LogHandler)
    print(f"Log server running on port {PORT}. Access it at http://localhost:{PORT}/run.jsonl")
    server.serve_forever()

def log_run(log_entry):
    log_entry["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open("run.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

def call_llm(conversation_history):
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    aiproxy_token = os.environ.get("AIPROXY_TOKEN")
    aipipe_token = os.environ.get("AIPIPE_TOKEN")

    system_prompt = (
        "You are a precise data analyst assistant. Your task is to write a self-contained Python script to solve a data analysis question.\n"
        "Rules for your Python code:\n"
        "1. It must be completely self-contained. Do not assume any external files exist unless the user specifies a URL.\n"
        "2. It must print ONLY a JSON object to standard output representing the final answer.\n"
        "3. If the question asks for a specific shape, e.g. {\"state\": ...} or {\"values\": [...]}, your printed JSON must match that shape EXACTLY.\n"
        "4. If the question points to a public dataset URL (e.g. MOSPI, raw CSV/JSON on GitHub, etc.), write code to download it using pandas (e.g., pd.read_csv('URL')) or urllib.\n"
        "5. If the question embeds data inline, parse it directly in python.\n"
        "6. Do not print any other text, warnings, or explanations. Use try-except blocks where appropriate, but make sure the final output is just the valid JSON object.\n"
        "7. Wrap your entire code in a markdown block:\n"
        "```python\n"
        "<your code>\n"
        "```\n"
    )

    prompt = f"{system_prompt}\n\nConversation history:\n{conversation_history}\n\nPython Code:"

    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["candidates"][0]["content"]["parts"][0]["text"]

    elif aiproxy_token:
        url = "https://aiproxy.sanand.workers.dev/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {aiproxy_token}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": conversation_history}
            ]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"]

    elif aipipe_token:
        url = "https://aipipe.org/openai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {aipipe_token}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": conversation_history}
            ]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"]

    elif openai_key:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_key}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": conversation_history}
            ]
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=60, context=ssl_context) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res["choices"][0]["message"]["content"]

    else:
        raise ValueError("No LLM API keys configured! Please set GEMINI_API_KEY, AIPROXY_TOKEN, AIPIPE_TOKEN, or OPENAI_API_KEY.")

def extract_code(text):
    match = re.search(r"```python\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()

def run_python_code(code_str):
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(code_str)
        temp_file_name = f.name
        
    try:
        res = subprocess.run([sys.executable, temp_file_name], capture_output=True, text=True, timeout=120)
        return res.stdout, res.stderr, res.returncode
    except subprocess.TimeoutExpired as e:
        return "", f"Execution Timeout: {e}", -1
    finally:
        try:
            os.remove(temp_file_name)
        except Exception:
            pass

def extract_json(text):
    text_clean = text.strip()
    try:
        return json.loads(text_clean)
    except json.JSONDecodeError:
        pass
    
    # Try finding curly braces block
    match = re.search(r"(\{.*\})", text_clean, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
            
    # Regex search for all candidate json-like substrings
    matches = re.findall(r"(\{.*?\})", text_clean, re.DOTALL)
    for m in reversed(matches):
        try:
            return json.loads(m.strip())
        except json.JSONDecodeError:
            continue
            
    return None

def send_telegram_reply(chat_id, text, reply_to_message_id=None):
    url = f"{API_URL}sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    req = urllib.request.Request(url, data=urllib.parse.urlencode(payload).encode("utf-8"))
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")
        return None

def process_message(chat_id, message_id, text):
    print(f"[{chat_id}] Received question: {text}")
    
    # Build context history
    with history_lock:
        if chat_id not in chat_histories:
            chat_histories[chat_id] = []
        chat_histories[chat_id].append({"role": "user", "text": text})
        
        # Format history for LLM
        history_str = ""
        for item in chat_histories[chat_id][-10:]:  # Last 10 turns
            history_str += f"{item['role'].upper()}: {item['text']}\n"
            
    try:
        # Step 1: Call LLM to write code
        llm_response = call_llm(history_str)
        python_code = extract_code(llm_response)
        
        print(f"[{chat_id}] Generated code:\n{python_code}")
        
        # Step 2: Execute python code
        stdout, stderr, exit_code = run_python_code(python_code)
        
        print(f"[{chat_id}] Code stdout:\n{stdout}")
        if stderr:
            print(f"[{chat_id}] Code stderr:\n{stderr}")
            
        # Step 3: Extract final JSON
        extracted_answer = extract_json(stdout)
        
        if extracted_answer is None:
            # Fallback if execution failed or no JSON was printed
            error_msg = f"Failed to extract JSON from stdout. Stderr: {stderr}"
            print(f"[{chat_id}] {error_msg}")
            extracted_answer = {"error": error_msg, "stdout": stdout, "stderr": stderr}
            
        # Clear history if it looks like a final response or keep it rolling?
        # Let's keep it rolling but limit to 10 turns.
        
        # Step 4: Construct reply
        host_url = PUBLIC_URL or f"http://localhost:{PORT}"
        log_url = f"{host_url}/run.jsonl"
        
        reply_json = {
            "answer": extracted_answer,
            "log_url": log_url
        }
        
        reply_text = json.dumps(reply_json)
        
        # Add to history
        with history_lock:
            chat_histories[chat_id].append({"role": "assistant", "text": reply_text})
            
        # Step 5: Send Telegram message
        send_telegram_reply(chat_id, reply_text, reply_to_message_id=message_id)
        
        # Step 6: Log run details
        log_entry = {
            "chat_id": chat_id,
            "message_id": message_id,
            "question": text,
            "generated_code": python_code,
            "code_stdout": stdout,
            "code_stderr": stderr,
            "exit_code": exit_code,
            "extracted_answer": extracted_answer,
            "reply_sent": reply_text
        }
        log_run(log_entry)
        print(f"[{chat_id}] Successfully handled request.")
        
    except Exception as e:
        err_detail = traceback.format_exc()
        print(f"[{chat_id}] Exception in process_message: {err_detail}")
        
        # Log failure
        log_entry = {
            "chat_id": chat_id,
            "message_id": message_id,
            "question": text,
            "error": str(e),
            "traceback": err_detail
        }
        log_run(log_entry)
        
        # Reply with error format
        host_url = PUBLIC_URL or f"http://localhost:{PORT}"
        reply_json = {
            "answer": {"error": str(e)},
            "log_url": f"{host_url}/run.jsonl"
        }
        send_telegram_reply(chat_id, json.dumps(reply_json), reply_to_message_id=message_id)

def poll_updates():
    offset = 0
    print("Telegram polling loop started...")
    while True:
        try:
            url = f"{API_URL}getUpdates?offset={offset}&timeout=30"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=35, context=ssl_context) as resp:
                updates = json.loads(resp.read().decode("utf-8"))
                if updates.get("ok") and updates.get("result"):
                    for update in updates["result"]:
                        offset = max(offset, update["update_id"] + 1)
                        if "message" in update:
                            msg = update["message"]
                            chat_id = msg["chat"]["id"]
                            message_id = msg["message_id"]
                            text = msg.get("text", "")
                            
                            # Start a thread to process message concurrently so we don't block polling
                            threading.Thread(target=process_message, args=(chat_id, message_id, text), daemon=True).start()
        except urllib.error.HTTPError as e:
            print(f"HTTP Error in polling updates: {e.code} {e.reason}")
            # If 401 Unauthorized, exit to avoid spamming
            if e.code == 401:
                print("Invalid BOT_TOKEN. Exiting.")
                os._exit(1)
            time.sleep(5)
        except urllib.error.URLError as e:
            import socket
            if isinstance(e.reason, socket.timeout):
                # Silence expected read timeout
                pass
            else:
                print(f"URL Error in polling updates: {e}")
                time.sleep(5)
        except Exception as e:
            print(f"Error in polling updates: {e}")
            time.sleep(5)
        time.sleep(0.5)

def main():
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN is required. Set BOT_TOKEN environment variable.")
        sys.exit(1)
        
    # Start web server thread
    threading.Thread(target=run_server, daemon=True).start()
    
    # Start Telegram polling
    poll_updates()

if __name__ == '__main__':
    main()
