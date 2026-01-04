import json
from typing import List, Literal
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

# --- 1. CONFIGURATION ---
llm = ChatOllama(model="qwen2.5:14b", temperature=0.3)

# --- 2. DATA MODELS ---

# A. INPUT MODELS
class QuestionTypeRequest(BaseModel):
    type: Literal["normal_multiple", "statement_verification", "statement_counting"]
    number: int

class QuizConfig(BaseModel):
    difficulty: Literal["easy", "medium", "hard"]
    quiz_type_config: List[QuestionTypeRequest]

class TopicPayload(BaseModel):
    topicName: str
    topicContent: str
    quiz_config: List[QuizConfig] 

# B. OUTPUT MODELS (Updated for Strict Typing)
class QuestionOption(BaseModel):
    id: str
    text: str

class QuizQuestion(BaseModel):
    id: int = Field(..., description="Question number")
    # ✅ FIX 1: Use Literal to force exact internal IDs
    type: Literal["normal_multiple", "statement_verification", "statement_counting"] = Field(
        ..., description="Must match the internal type ID exactly"
    )
    question_text: str = Field(..., description="The main question text including any statements")
    options: List[QuestionOption] = Field(..., description="List of options")
    correct_option_id: str = Field(..., description="The correct option ID (e.g., 'A')")
    explanation: str = Field(..., description="Detailed explanation of why the correct answer is right and why distractors are wrong")

class GeneratedQuiz(BaseModel):
    topic_title: str
    difficulty: str
    questions: List[QuizQuestion]

# --- 3. DYNAMIC PROMPT BUILDER ---
def build_type_instructions(question_types: List[str], difficulty: str) -> str:
    """
    Builds instructions with explicit JSON ID mapping.
    """
    instructions = []
    
    # 1. Define Logic based on Difficulty
    if difficulty.lower() == "easy":
        focus = "direct definitions and basic facts."
        stmt_logic = "Short, simple sentences directly from text."
        stmt_count = 3
        roman_block = "I. [Statement 1]\n           II. [Statement 2]\n           III. [Statement 3]"
        count_opts = "A) 0, B) 1, C) 2, D) 3"
        
    elif difficulty.lower() == "medium":
        focus = "concepts and comparisons."
        stmt_logic = "Paraphrased concepts or combinations."
        stmt_count = 3
        roman_block = "I. [Concept A]\n           II. [Concept B]\n           III. [Concept C]"
        count_opts = "A) 0, B) 1, C) 2, D) 3"

    else: # HARD
        focus = "edge cases and limitations."
        stmt_logic = "Logical deductions (If X then Y)."
        stmt_count = 4
        roman_block = "I. [Deduction 1]\n           II. [Deduction 2]\n           III. [Deduction 3]\n           IV. [Deduction 4]"
        count_opts = "A) 0, B) 1, C) 2, D) 3, E) 4"

    # 2. Build Instructions with Explicit ID Requirements

    if "normal_multiple" in question_types:
        instructions.append(f"""
        [TYPE: Normal Multiple Choice]
        - ✅ REQUIRED JSON 'type': "normal_multiple"
        - Complexity: {difficulty.upper()}
        - Goal: Focus on {focus}
        - Template:
           Question: [Question Text]?
           A) [Option 1] ... D) [Option 4]
        """)

    if "statement_verification" in question_types:
        instructions.append(f"""
        [TYPE: Statement Verification]
        - ✅ REQUIRED JSON 'type': "statement_verification"
        - Complexity: {difficulty.upper()}
        - Format: "Which of the following statements is TRUE?"
        """)

    if "statement_counting" in question_types:
        instructions.append(f"""
        [TYPE: Statement Counting]
        - ✅ REQUIRED JSON 'type': "statement_counting"
        - Complexity: {difficulty.upper()}
        - CRITICAL RULE: You must write the Roman Numeral statements INSIDE the 'question_text' field.
        - Logic: {stmt_logic}
        
        - Template for 'question_text' (Use Exactly):
           "Consider the following statements regarding [Topic]:
           {roman_block}
           
           How many of the statements above are TRUE?"
           
        - Template for 'options':
           {count_opts}
        """)

    return "\n".join(instructions)

# --- 4. GENERATION LOOP ---
def generate_quiz_for_topic(payload: TopicPayload):
    print(f"🚀 Processing Topic: {payload.topicName}")
    all_quizzes = []

    for config in payload.quiz_config:
        print(f"\n⚙️  Generating {config.difficulty.upper()} Quiz...")
        
        current_types = [item.type for item in config.quiz_type_config]
        
        # Build Count Requirements
        req_string = ""
        total_questions = 0
        for item in config.quiz_type_config:
            count = item.number
            q_type = item.type.replace("_", " ").title()
            req_string += f"- {count} questions of type '{q_type}' (Internal ID: {item.type})\n"
            total_questions += count

        dynamic_rules = build_type_instructions(current_types, config.difficulty)

        prompt = f"""
        You are a Professor creating a Exam Quiz.
        TOPIC: {payload.topicName}
        SOURCE MATERIAL:
        {payload.topicContent}
        
        TASK:
        Generate exactly {total_questions} questions based on the source text.
        
        DIFFICULTY SETTING: {config.difficulty.upper()}
        
        QUESTION BREAKDOWN:
        {req_string}
        
        STRICT RULES FOR EACH TYPE:
        {dynamic_rules}
        
        OUTPUT FORMAT:
        Return a valid JSON object matching the schema. 
        IMPORTANT: The 'type' field in JSON must match the Internal ID exactly (e.g. "normal_multiple").
        """

        try:
            quiz_result = llm.with_structured_output(GeneratedQuiz).invoke(prompt)
            
            # Metadata injection
            quiz_result.topic_title = payload.topicName
            quiz_result.difficulty = config.difficulty
            
            all_quizzes.append(quiz_result.dict())
            print(f"   ✅ Success! Generated {len(quiz_result.questions)} questions.")

        except Exception as e:
            print(f"   ❌ Error: {e}")

    return all_quizzes

# --- 5. TEST RUNNER ---
if __name__ == "__main__":
    mock_content = """
    Item 2: Consider a builder when faced with many constructor parameters.
    Static factories and constructors share a limitation: they do not scale well to large numbers of optional parameters.
    Traditionally, programmers have used the telescoping constructor pattern.
    A second alternative is the JavaBeans pattern. Unfortunately, the JavaBeans pattern precludes the possibility of making a class immutable.
    Luckily, there is a third alternative: the Builder pattern. The client calls a constructor with required parameters and gets a builder object.
    Then the client calls setter-like methods. Finally, the client calls a parameterless build method. The Builder pattern simulates named optional parameters.
    """

    request_data = {
      "topicName": "Item 2: Builder Pattern",
      "topicContent": mock_content,
      "quiz_config": [
        {
          "difficulty": "medium",
          "quiz_type_config": [
            { "type": "normal_multiple", "number": 1 },
            { "type": "statement_verification", "number": 1 }
          ]
        },
        {
          "difficulty": "hard",
          "quiz_type_config": [
            { "type": "statement_counting", "number": 1 }
          ]
        }
      ]
    }

    payload = TopicPayload(**request_data)
    results = generate_quiz_for_topic(payload)

    print("\n" + "="*50)
    for quiz in results:
        print(f"📝 {quiz['difficulty'].upper()} QUIZ OUTPUT:")
        for q in quiz['questions']:
            # Validate that 'type' is exactly what we wanted
            print(f"  [{q['type']}] {q['question_text']}")
            print(f"   (Type ID Verification: '{q['type']}')") 
            for opt in q['options']:
                print(f"    {opt['id']}) {opt['text']}")
            print(f"  ✅ Correct Option: {q['correct_option_id']}")
            print(f"  ℹ️  Explanation: {q['explanation']}")
            print("-" * 30)