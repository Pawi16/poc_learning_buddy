import json
from typing import List, Literal
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

# --- 1. CONFIGURATION ---
llm = ChatOllama(model="qwen2.5:14b", temperature=0.3)

# --- 2. DATA MODELS ---

# A. INPUT MODEL (Simplified: One Topic + Amount)
class FlashcardConfig(BaseModel):
    amount: int = Field(..., description="Number of cards to generate for this topic")

class TopicPayload(BaseModel):
    topicName: str
    topicContent: str
    config: FlashcardConfig

# B. OUTPUT MODEL
class FlashcardItem(BaseModel):
    id: int = Field(..., description="Card sequence number (1, 2, 3...)")
    front_text: str = Field(..., description="The question, term, or concept (Front side)")
    back_text: str = Field(..., description="The answer, definition, or explanation (Back side)")
    category: Literal["Definition", "Concept", "Code", "Pro/Con"] = Field(..., description="Type of information")

class FlashcardDeck(BaseModel):
    topic_title: str
    cards: List[FlashcardItem]

# --- 3. GENERATION LOGIC ---
def generate_flashcard_deck(payload: TopicPayload):
    print(f"🚀 Generating Deck for: {payload.topicName} ({payload.config.amount} cards)")
    
    # We default to a "Balanced" mix since there is no difficulty selection
    prompt = f"""
    You are an Expert Tutor creating a Flashcard Deck for a student.
    
    TOPIC: {payload.topicName}
    SOURCE MATERIAL:
    {payload.topicContent}
    
    TASK:
    Create exactly {payload.config.amount} high-quality flashcards to help the student memorize the key concepts from the text.
    
    GUIDELINES:
    1. **Focus:** Cover the most important definitions, advantages, disadvantages, and code concepts.
    2. **Front Side:** Should be a specific question or term (e.g., "What is the main advantage of X?").
    3. **Back Side:** Should be concise and accurate (1-2 sentences).
    
    ⛔ SELF-CONTAINED RULE (CRITICAL):
    - Do NOT say "In the text above..." or "As mentioned...".
    - The card must make sense in isolation.
    - BAD Back: "It is used to create objects." (What is 'It'?)
    - GOOD Back: "The Builder Pattern is used to create objects..."
    
    ⛔ DIVERSITY RULE:
    - Each card must cover a DIFFERENT fact. Do not repeat the same concept twice.
    
    OUTPUT FORMAT:
    Return a valid JSON object matching the 'FlashcardDeck' schema.
    """

    # Retry Loop (Standard Stability Pattern)
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            deck_result = llm.with_structured_output(FlashcardDeck).invoke(prompt)
            
            # Metadata injection
            deck_result.topic_title = payload.topicName
            
            # Validation: Did we get enough cards?
            if len(deck_result.cards) < payload.config.amount:
                print(f"   ⚠️ Warning: Requested {payload.config.amount}, got {len(deck_result.cards)}")
            
            print(f"   ✅ Success! Generated {len(deck_result.cards)} flashcards.")
            return deck_result.dict()

        except Exception as e:
            print(f"   ⚠️ Error on attempt {attempt+1}: {e}")
            if attempt == max_retries:
                print("   ❌ Failed to generate deck.")
                return None

# --- 4. TEST RUNNER ---
if __name__ == "__main__":
    # Mock Content (Effective Java Snippet)
    mock_content = """
    Static factories and constructors share a limitation: they do not scale well to large\nnumbers of optional parameters. Consider the case of a class representing the\nNutrition Facts label that appears on packaged foods. These labels have a few\nrequired fields—serving size, servings per container, and calories per serving—\nand more than twenty optional fields—total fat, saturated fat, trans fat, cholesterol,\nsodium, and so on. Most products have nonzero values for only a few of these\noptional fields.\nWhat sort of constructors or static factories should you write for such a class?\nTraditionally, programmers have used the telescoping constructor pattern, in\nwhich you provide a constructor with only the required parameters, another with a\nsingle optional parameter, a third with two optional parameters, and so on, culmi-\nnating in a constructor with all the optional parameters. Here’s how it looks in\npractice. For brevity’s sake, only four optional fields are shown:\n// Telescoping constructor pattern - does not scale well!\npublic class NutritionFacts {\nprivate final int servingSize; // (mL) required\nprivate final int servings; // (per container) required\nprivate final int calories; // (per serving) optional\nprivate final int fat; // (g/serving) optional\nprivate final int sodium; // (mg/serving) optional\nprivate final int carbohydrate; // (g/serving) optional\npublic NutritionFacts(int servingSize, int servings) {\nthis(servingSize, servings, 0);\n}\npublic NutritionFacts(int servingSize, int servings,\nint calories) {\nthis(servingSize, servings, calories, 0);\n}\npublic NutritionFacts(int servingSize, int servings,\nint calories, int fat) {\nthis(servingSize, servings, calories, fat, 0);\n}\npublic NutritionFacts(int servingSize, int servings,\nint calories, int fat, int sodium) {\nthis(servingSize, servings, calories, fat, sodium, 0);\n}\nITEM 2: CONSIDER A BUILDER WHEN FACED WITH MANY CONSTRUCTOR PARAMETERS 11\npublic NutritionFacts(int servingSize, int servings,\nint calories, int fat, int sodium, int carbohydrate) {\nthis.servingSize = servingSize;\nthis.servings = servings;\nthis.calories = calories;\nthis.fat = fat;\nthis.sodium = sodium;\nthis.carbohydrate = carbohydrate;\n}\n}\nWhen you want to create an instance, you use the constructor with the shortest\nparameter list containing all the parameters you want to set:\nNutritionFacts cocaCola =\nnew NutritionFacts(240, 8, 100, 0, 35, 27);\nTypically this constructor invocation will require many parameters that you don’t\nwant to set, but you’re forced to pass a value for them anyway. In this case, we\npassed a value of 0 for fat . With “only” six parameters this may not seem so bad,\nbut it quickly gets out of hand as the number of parameters increases.\nIn short, the telescoping constructor pattern works, but it is hard to write\nclient code when there are many parameters, and harder still to read it. The\nreader is left wondering what all those values mean and must carefully count\nparameters to find out. Long sequences of identically typed parameters can cause\nsubtle bugs. If the client accidentally reverses two such parameters, the compiler\nwon’t complain, but the program will misbehave at runtime (Item51).\nA second alternative when you’re faced with many optional parameters in a\nconstructor is the JavaBeans pattern, in which you call a parameterless construc-\ntor to create the object and then call setter methods to set each required parameter\nand each optional parameter of interest:\n// JavaBeans Pattern - allows inconsistency, mandates mutability\npublic class NutritionFacts {\n// Parameters initialized to default values (if any)\nprivate int servingSize = -1; // Required; no default value\nprivate int servings = -1; // Required; no default value\nprivate int calories = 0;\nprivate int fat = 0;\nprivate int sodium = 0;\nprivate int carbohydrate = 0;\npublic NutritionFacts() { }\nCHAPTER2 CREATING AND DESTROYING OBJECTS 12\n// Setters\npublic void setServingSize(int val) { servingSize = val; }\npublic void setServings(int val) { servings = val; }\npublic void setCalories(int val) { calories = val; }\npublic void setFat(int val) { fat = val; }\npublic void setSodium(int val) { sodium = val; }\npublic void setCarbohydrate(int val) { carbohydrate = val; }\n}\nThis pattern has none of the disadvantages of the telescoping constructor pattern.\nIt is easy, if a bit wordy, to create instances, and easy to read the resulting code:\nNutritionFacts cocaCola = new NutritionFacts();\ncocaCola.setServingSize(240);\ncocaCola.setServings(8);\ncocaCola.setCalories(100);\ncocaCola.setSodium(35);\ncocaCola.setCarbohydrate(27);\nUnfortunately, the JavaBeans pattern has serious disadvantages of its own.\nBecause construction is split across multiple calls, a JavaBean may be in an\ninconsistent state partway through its construction. The class does not have\nthe option of enforcing consistency merely by checking the validity of the\nconstructor parameters. Attempting to use an object when it’s in an inconsistent\nstate may cause failures that are far removed from the code containing the bug and\nhence difficult to debug. A related disadvantage is that the JavaBeans pattern\nprecludes the possibility of making a class immutable (Item17) and requires\nadded effort on the part of the programmer to ensure thread safety.\nIt is possible to reduce these disadvantages by manually “freezing” the object\nwhen its construction is complete and not allowing it to be used until frozen, but\nthis variant is unwieldy and rarely used in practice. Moreover, it can cause errors\nat runtime because the compiler cannot ensure that the programmer calls the\nfreeze method on an object before using it.\nLuckily, there is a third alternative that combines the safety of the telescoping\nconstructor pattern with the readability of the JavaBeans pattern. It is a form of the\nBuilder pattern [Gamma95]. Instead of making the desired object directly, the\nclient calls a constructor (or static factory) with all of the required parameters and\ngets a builder object . Then the client calls setter-like methods on the builder object\nto set each optional parameter of interest. Finally, the client calls a parameterless\nbuild method to generate the object, which is typically immutable. The builder is\ntypically a static member class (Item24) of the class it builds. Here’s how it looks\nin practice:\nITEM 2: CONSIDER A BUILDER WHEN FACED WITH MANY CONSTRUCTOR PARAMETERS 13\n// Builder Pattern\npublic class NutritionFacts {\nprivate final int servingSize;\nprivate final int servings;\nprivate final int calories;\nprivate final int fat;\nprivate final int sodium;\nprivate final int carbohydrate;\npublic static class Builder {\n// Required parameters\nprivate final int servingSize;\nprivate final int servings;\n// Optional parameters - initialized to default values\nprivate int calories = 0;\nprivate int fat = 0;\nprivate int sodium = 0;\nprivate int carbohydrate = 0;\npublic Builder(int servingSize, int servings) {\nthis.servingSize = servingSize;\nthis.servings = servings;\n}\npublic Builder calories(int val)\n{ calories = val; return this; }\npublic Builder fat(int val)\n{ fat = val; return this; }\npublic Builder sodium(int val)\n{ sodium = val; return this; }\npublic Builder carbohydrate(int val)\n{ carbohydrate = val; return this; }\npublic NutritionFacts build() {\nreturn new NutritionFacts(this);\n}\n}\nprivate NutritionFacts(Builder builder) {\nservingSize = builder.servingSize;\nservings = builder.servings;\ncalories = builder.calories;\nfat = builder.fat;\nsodium = builder.sodium;\ncarbohydrate = builder.carbohydrate;\n}\n}\nCHAPTER2 CREATING AND DESTROYING OBJECTS 14\nThe NutritionFacts class is immutable, and all parameter default values are\nin one place. The builder’s setter methods return the builder itself so that invoca-\ntions can be chained, resulting in a fluent API . Here’s how the client code looks:\nNutritionFacts cocaCola = new NutritionFacts.Builder(240, 8)\n.calories(100).sodium(35).carbohydrate(27).build();\nThis client code is easy to write and, more importantly, easy to read. The Builder\npattern simulates named optional parameters as found in Python and Scala.\nValidity checks were omitted for brevity. To detect invalid parameters as soon\nas possible, check parameter validity in the builder’s constructor and methods.\nCheck invariants involving multiple parameters in the constructor invoked by the\nbuild method. To ensure these invariants against attack, do the checks on object\nfields after copying parameters from the builder (Item50). If a check fails, throw\nan IllegalArgumentException (Item72) whose detail message indicates which\nparameters are invalid (Item75).\nThe Builder pattern is well suited to class hierarchies. Use a parallel hier-\narchy of builders, each nested in the corresponding class. Abstract classes have\nabstract builders; concrete classes have concrete builders. For example, consider\nan abstract class at the root of a hierarchy representing various kinds of pizza:\n// Builder pattern for class hierarchies\npublic abstract class Pizza {\npublic enum Topping { HAM, MUSHROOM, ONION, PEPPER, SAUSAGE }\nfinal Set<Topping> toppings;\nabstract static class Builder<T extends Builder<T>> {\nEnumSet<Topping> toppings = EnumSet.noneOf(Topping.class);\npublic T addTopping(Topping topping) {\ntoppings.add(Objects.requireNonNull(topping));\nreturn self();\n}\nabstract Pizza build();\n// Subclasses must override this method to return \"this\"\nprotected abstract T self();\n}\nPizza(Builder<?> builder) {\ntoppings = builder.toppings.clone(); // See Item 50\n}\n}\nNote that Pizza.Builder is a generic type with a recursive type parameter\n(Item30). This, along with the abstract self method, allows method chaining to\nwork properly in subclasses, without the need for casts. This workaround for the\nfact that Java lacks a self type is known as the simulated self-type idiom.\nITEM 2: CONSIDER A BUILDER WHEN FACED WITH MANY CONSTRUCTOR PARAMETERS 15\nHere are two concrete subclasses of Pizza , one of which represents a standard\nNew-York-style pizza, the other a calzone. The former has a required size parame-\nter, while the latter lets you specify whether sauce should be inside or out:\npublic class NyPizza extends Pizza {\npublic enum Size { SMALL, MEDIUM, LARGE }\nprivate final Size size;\npublic static class Builder extends Pizza.Builder<Builder> {\nprivate final Size size;\npublic Builder(Size size) {\nthis.size = Objects.requireNonNull(size);\n}\n@Override public NyPizza build() {\nreturn new NyPizza(this);\n}\n@Override protected Builder self() { return this; }\n}\nprivate NyPizza(Builder builder) {\nsuper(builder);\nsize = builder.size;\n}\n}\npublic class Calzone extends Pizza {\nprivate final boolean sauceInside;\npublic static class Builder extends Pizza.Builder<Builder> {\nprivate boolean sauceInside = false; // Default\npublic Builder sauceInside() {\nsauceInside = true;\nreturn this;\n}\n@Override public Calzone build() {\nreturn new Calzone(this);\n}\n@Override protected Builder self() { return this; }\n}\nprivate Calzone(Builder builder) {\nsuper(builder);\nsauceInside = builder.sauceInside;\n}\n}\nCHAPTER2 CREATING AND DESTROYING OBJECTS 16\nNote that the build method in each subclass’s builder is declared to return the\ncorrect subclass: the build method of NyPizza.Builder returns NyPizza , while\nthe one in Calzone.Builder returns Calzone . This technique, wherein a subclass\nmethod is declared to return a subtype of the return type declared in the super-\nclass, is known as covariant return typing . It allows clients to use these builders\nwithout the need for casting.\nThe client code for these “hierarchical builders” is essentially identical to the\ncode for the simple NutritionFacts builder. The example client code shown next\nassumes static imports on enum constants for brevity:\nNyPizza pizza = new NyPizza.Builder(SMALL)\n.addTopping(SAUSAGE).addTopping(ONION).build();\nCalzone calzone = new Calzone.Builder()\n.addTopping(HAM).sauceInside().build();\nA minor advantage of builders over constructors is that builders can have mul-\ntiple varargs parameters because each parameter is specified in its own method.\nAlternatively, builders can aggregate the parameters passed into multiple calls to a\nmethod into a single field, as demonstrated in the addTopping method earlier.\nThe Builder pattern is quite flexible. A single builder can be used repeatedly\nto build multiple objects. The parameters of the builder can be tweaked between\ninvocations of the build method to vary the objects that are created. A builder can\nfill in some fields automatically upon object creation, such as a serial number that\nincreases each time an object is created.\nThe Builder pattern has disadvantages as well. In order to create an object, you\nmust first create its builder. While the cost of creating this builder is unlikely to be\nnoticeable in practice, it could be a problem in performance-critical situations.\nAlso, the Builder pattern is more verbose than the telescoping constructor pattern,\nso it should be used only if there are enough parameters to make it worthwhile, say\nfour or more. But keep in mind that you may want to add more parameters in the\nfuture. But if you start out with constructors or static factories and switch to a\nbuilder when the class evolves to the point where the number of parameters gets\nout of hand, the obsolete constructors or static factories will stick out like a sore\nthumb. Therefore, it’s often better to start with a builder in the first place.\nIn summary, the Builder pattern is a good choice when designing classes\nwhose constructors or static factories would have more than a handful of\nparameters , especially if many of the parameters are optional or of identical type.\nClient code is much easier to read and write with builders than with telescoping\nconstructors, and builders are much safer than JavaBeans.\nITEM 3: ENFORCE THE SINGLETON PROPERTY WITH A PRIVATE CONSTRUCTOR OR AN ENUM TYPE 17
    """

    # User Request: "Give me 5 cards about Builder Pattern"
    request_data = {
      "topicName": "Item 2: Builder Pattern",
      "topicContent": mock_content,
      "config": {
        "amount": 5
      }
    }

    payload = TopicPayload(**request_data)
    result = generate_flashcard_deck(payload)

    if result:
        print("\n" + "="*50)
        print(f"📇 DECK: {result['topic_title']}")
        print("="*50)
        for card in result['cards']:
            print(f"\n[FRONT]: {card['front_text']}")
            print(f"[BACK]:  {card['back_text']}")
            print(f"[TAG]:   {card['category']}")
            print("-" * 30)