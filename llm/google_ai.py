import os
from typing import List, Dict
import logging
import google.genai as genai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google AI integration class
class GoogleAIIntegration:
    def __init__(self, api_key: str = None, model_name: str = "gemini-1.5-flash", system_prompt: str = None, safety_settings: Dict = None):
        self.api_key = api_key or os.getenv('GOOGLE_AI_API_KEY')
        self.model_name = model_name
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        self.safety_settings = safety_settings or self._get_default_safety_settings()
        self.client = None
        
        if not self.api_key:
            raise ValueError("Google AI API key is required. Set GOOGLE_AI_API_KEY environment variable or pass api_key parameter.")
        
        self._initialise_client()
    
    def _get_default_system_prompt(self) -> str:
        return """You are a helpful AI assistant in a RAG (Retrieval-Augmented Generation) chatbot system. 
        
Your role is to:
- Provide accurate, helpful, and relevant responses to user questions
- Use information from the conversation history to maintain context
- Be concise but comprehensive in your answers
- Ask clarifying questions when needed
- Admit when you don't know something rather than making up information
- Maintain a friendly and professional tone

Always strive to be helpful while being truthful and accurate."""
    
    def _get_default_safety_settings(self) -> List[genai.types.SafetySetting]:
        return [
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
            ),
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
            ),
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
            ),
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
            )
        ]
    
    def create_custom_safety_settings(self, harassment_level: str = "BLOCK_LOW_AND_ABOVE", hate_speech_level: str = "BLOCK_LOW_AND_ABOVE", sexually_explicit_level: str = "BLOCK_LOW_AND_ABOVE", dangerous_content_level: str = "BLOCK_LOW_AND_ABOVE") -> List[genai.types.SafetySetting]:
        threshold_map = {
            "BLOCK_NONE": genai.types.HarmBlockThreshold.BLOCK_NONE,
            "BLOCK_ONLY_HIGH": genai.types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            "BLOCK_MEDIUM_AND_ABOVE": genai.types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            "BLOCK_LOW_AND_ABOVE": genai.types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE
        }
        
        return [
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=threshold_map[harassment_level]
            ),
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=threshold_map[hate_speech_level]
            ),
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=threshold_map[sexually_explicit_level]
            ),
            genai.types.SafetySetting(
                category=genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=threshold_map[dangerous_content_level]
            )
        ]
        
    def _initialise_client(self):
        try:
            self.client = genai.Client(api_key=self.api_key)
            logger.info(f"Successfully initialized Google AI client with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Google AI client: {str(e)}")
            raise
    
    def generate_response(self, prompt: str, conversation_history: List[Dict] = None, max_tokens: int = 3000, temperature: float = 0.1, custom_system_prompt: str = None, custom_safety_settings: List[genai.types.SafetySetting] = None) -> str:
        try:
            # Build the conversation turns from history
            messages = self._build_messages_with_history(prompt, conversation_history)
            

            system_instruction = custom_system_prompt or self.system_prompt
            safety_settings = custom_safety_settings or self.safety_settings
            
            # Configure generation parameters
            config = genai.types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
                top_p=0.95,
                top_k=40,
                system_instruction=system_instruction,
                safety_settings=safety_settings
            )
            
            # Generate response
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=messages,
                config=config
            )
            
            # Check if input was blocked by safety filters
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                if hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                    logger.warning(f"Input Content blocked by safety filter: {response.prompt_feedback.block_reason}")
                    return "I'm sorry, but I can't provide a response to that request due to content safety filters.", 0

            # Check if we have candidates
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                
                # Check if response was blocked by safety filters
                if hasattr(candidate, 'finish_reason') and candidate.finish_reason == genai.types.FinishReason.SAFETY:
                    # Get detailed safety information
                    blocked_categories = []
                    if hasattr(candidate, 'safety_ratings'):
                        for rating in candidate.safety_ratings:
                            if hasattr(rating, 'blocked') and rating.blocked:
                                category_name = rating.category.name.replace('HARM_CATEGORY_', '').lower().replace('_', ' ')
                                blocked_categories.append(category_name)
                    
                    if blocked_categories:
                        logger.warning(f"Response blocked by safety filter for: {', '.join(blocked_categories)}")
                    else:
                        logger.warning("Response blocked by safety filter")
                    
                    return "I'm sorry, but I can't complete the response due to content safety filters.", 0
                
                # Check if we have content parts
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                    response_text = candidate.content.parts[0].text
                    logger.info(f"Generated response for prompt: {prompt[:50]}...")
                    return response_text.strip(), 1
                else:
                    logger.warning("Empty content parts from Google AI")
                    return "I apologise, but I couldn't generate a response at the moment. Please try again.", 0
            else:
                logger.warning("No candidates in response from Google AI")
                return "I apologise, but I couldn't generate a response at the moment. Please try again.", 0
                
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return f"I encountered an error while processing your request. Please try again later.", 0
    
    def _build_messages_with_history(self, current_prompt: str, conversation_history: List[Dict] = None) -> List[genai.types.Content]:
        messages = []
        
        # Add conversation history (keep only last 5 turns to manage context length)
        if conversation_history:
            for turn in conversation_history[-5:]:
                if 'question' in turn and 'answer' in turn:
                    # Add user message
                    messages.append(genai.types.Content(
                        role='user',
                        parts=[genai.types.Part(text=turn['question'])]
                    ))
                    # Add assistant response
                    messages.append(genai.types.Content(
                        role='model',
                        parts=[genai.types.Part(text=turn['answer'])]
                    ))
        
        # Add current user message
        messages.append(genai.types.Content(
            role='user',
            parts=[genai.types.Part(text=current_prompt)]
        ))
        
        return messages
    
# Global Google AI instance
google_ai_instance = None

def setup_google_ai_client(app, model_name: str = "gemini-1.5-flash", system_prompt: str = None, safety_settings: Dict = None):
    global google_ai_instance
    
    try:
        google_ai_instance = GoogleAIIntegration(
            api_key=os.getenv('GOOGLE_AI_API_KEY'), 
            model_name=model_name, 
            system_prompt=system_prompt,
            safety_settings=safety_settings
        )
        
        # Store in app config for access in routes
        app.config['GOOGLE_AI_INSTANCE'] = google_ai_instance
        
        logger.info("Google AI client setup completed successfully")
        return google_ai_instance
        
    except Exception as e:
        logger.error(f"Failed to setup Google AI client: {str(e)}")
        raise

def generate_ai_response(prompt: str, conversation_history: List[Dict] = None, max_tokens: int = 3000, temperature: float = 0.1, custom_system_prompt: str = None) -> str:
    global google_ai_instance
    
    if not google_ai_instance:
        logger.error("Google AI client not initialised.")
        return "Google AI service is not available at the moment."
    
    return google_ai_instance.generate_response(
        prompt=prompt,
        conversation_history=conversation_history,
        max_tokens=max_tokens,
        temperature=temperature,
        custom_system_prompt=custom_system_prompt,
        custom_safety_settings=google_ai_instance._get_default_safety_settings()
    )
