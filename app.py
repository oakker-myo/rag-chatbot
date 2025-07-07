from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import uuid
from datetime import datetime
import time
import random
import logging
import atexit
# Import database components
from database.database import init_database, close_database, session_dao, message_dao
# Import JSON utilities
from json_utils import safe_json_response, DateTimeEncoder
# Import vector database components
from vectordb.qdrant_vector_db import index_documents_standalone
# Import AI components
from llm.google_ai import setup_google_ai_client
from llm.promptflow import generate_promptflow_response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.json_encoder = DateTimeEncoder
socketio = SocketIO(app, cors_allowed_origins="*")

# Initialize database on startup
if not init_database():
    logger.error("Failed to initialise database. Exiting...")
    exit(1)

# Close database connection on exit
atexit.register(close_database)

# Setup Google AI integration
setup_google_ai_client(app, model_name="gemini-2.0-flash")

@app.route('/')
def index():
    welcome_message_pairs = [
        ["Hello!", "How can I help you today?"],
        ["Hi there!", "What can I assist you with?"],
        ["Greetings!", "Feel free to ask me anything."],
        ["Pleased to meet you!", "I'm ready to answer your questions."],
        ["Welcome aboard!", "Let me know how I can be of service."]
    ]
    welcome_message = random.choice(welcome_message_pairs)
    return render_template('index.html', welcome_message=welcome_message)

@socketio.on('connect')
def on_connect():
    logger.info(f'Client connected: {request.sid}')

@socketio.on('disconnect')
def on_disconnect():
    logger.info(f'Client disconnected: {request.sid}')

@socketio.on('join_session')
def on_join_session(data):
    try:
        session_id = data.get('session_id')
        
        if not session_id:
            session_id = 'session_' + str(int(time.time())) + '_' + str(uuid.uuid4())[:8]
        
        # Try to get existing session
        session_data = session_dao.get_session(session_id)
        
        if not session_data:
            # Create new session
            session_data = session_dao.create_session(
                session_id=session_id,
                metadata={'client_sid': request.sid}
            )
            logger.info(f"Created new session: {session_id}")
        else:
            logger.info(f"Joined existing session: {session_id}")
        
        # Get message history
        messages = message_dao.get_messages_by_session(session_id)
        
        # Send session info and message history back to client
        emit('session_initialised', {
            'session_id': session_id,
            'session_data': safe_json_response(session_data),
            'messages': safe_json_response(messages)
        })
        
    except Exception as e:
        logger.error(f"Error in join_session: {e}")
        emit('error', {'message': 'Failed to initialise session'})

@socketio.on('user_message')
def handle_user_message(data):
    try:
        session_id = data.get('session_id')
        user_message = data.get('message', '').strip()
        
        if not session_id or not user_message:
            emit('error', {'message': 'Invalid session or message'})
            return
        
        # Get or create session
        session_data = session_dao.get_session(session_id)
        if not session_data:
            session_data = session_dao.create_session(session_id)
        
        message_start_time = datetime.now()
        
        # Get current message count
        existing_messages = message_dao.get_messages_by_session(session_id)
        current_message_count = len(existing_messages) + 1
        
        # Build conversation history for AI
        conversation_history = []
        for msg in existing_messages:
            conversation_history.append({
                'question': msg['question'],
                'answer': msg['answer']
            })
        
        # Generate AI response
        ai_response, sources = generate_promptflow_response(user_message, conversation_history)
        
        # Calculate response duration
        response_end_time = datetime.now()
        duration = (response_end_time - message_start_time).total_seconds()
        
        # Create message data
        message_data = {
            'id': f"{session_id}_{current_message_count}",
            'session_id': session_id,
            'history': conversation_history,
            'timestamp': message_start_time.isoformat(),
            'duration': duration,
            'message_count': current_message_count,
            'question': user_message,
            'answer': ai_response,
            'sources': sources
        }
        
        # Save message to database
        saved_message = message_dao.create_message(message_data)
        
        # Update session conversation data and end timestamp
        updated_conversation = conversation_history + [{
            'question': user_message,
            'answer': ai_response
        }]
        
        updated_session = session_dao.update_session(
            session_id=session_id,
            conversation_data=updated_conversation,
            end_timestamp=response_end_time
        )
        
        # Send response back to client
        emit('ai_response', {
            'message_data': safe_json_response(saved_message),
            'session_data': safe_json_response(updated_session)
        })
        
        logger.info(f"Session {session_id}: Q: {user_message[:50]}... A: {ai_response[:50]}...")
        
    except Exception as e:
        logger.error(f"Error handling user message: {e}")
        emit('error', {'message': 'Failed to process message'})

@socketio.on('end_session')
def handle_end_session(data):
    try:
        session_id = data.get('session_id')
        
        if session_id:
            # Update session end timestamp
            session_dao.update_session(
                session_id=session_id,
                end_timestamp=datetime.now()
            )
            emit('session_ended', {'session_id': session_id})
            logger.info(f"Session ended: {session_id}")
            
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        emit('error', {'message': 'Failed to end session'})

if __name__ == '__main__':
    result = index_documents_standalone("./documents", overwrite=True)
    logger.info(f"Document indexing result: {result['status']}")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)