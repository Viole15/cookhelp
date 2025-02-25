from flask import Flask, render_template, request
import requests
import json
import re
from bs4 import BeautifulSoup
from functools import wraps
import time

app = Flask(__name__)

# API Keys
SPOONACULAR_API_KEY = "7432dc450b8b4dafa8fd40a15b8df66b"
GEMINI_API_KEY = "AIzaSyCixC_R7gi-bs8iX4uuR0Pc6JXuVBPIYsc"

# Spoonacular API Endpoints
SPOONACULAR_SEARCH_URL = "https://api.spoonacular.com/recipes/complexSearch"

# Retry decorator
def retry(max_retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"Retry {retries + 1} for {func.__name__}: {str(e)}")
                    time.sleep(delay)
                    retries += 1
            return []
        return wrapper
    return decorator

@retry(max_retries=2)
def get_spoonacular_recipes(query):
    try:
        formatted_query = query.strip().replace(", ", ",")
        params = {
            "apiKey": SPOONACULAR_API_KEY,
            "query": formatted_query,
            "number": 10,
            "addRecipeInformation": True,
            "addRecipeNutrition": True,
            "fillIngredients": True,
            "instructionsRequired": True
        }
        response = requests.get(SPOONACULAR_SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        recipes = []
        for result in data.get('results', []):
            try:
                nutrients = {nutrient['name']: nutrient['amount'] for nutrient in result.get('nutrition', {}).get('nutrients', [])}
                recipe = {
                    "title": result.get('title'),
                    "image": result.get('image'),
                    "ingredients": [{
                        "name": ing['name'],
                        "usMeasurement": f"{ing['measures']['us']['amount']} {ing['measures']['us']['unitShort']}",
                        "metricMeasurement": f"{ing['measures']['metric']['amount']} {ing['measures']['metric']['unitShort']}"
                    } for ing in result.get('extendedIngredients', [])],
                    "instructions": [step['step'] for step in result.get('analyzedInstructions', [{}])[0].get('steps', [])],
                    "timeCategory": "Medium",
                    "culturalOrigin": result.get('cuisines', ['International'])[0] if result.get('cuisines') else "International",
                    "source": "Spoonacular",
                    "nutrition": {
                        "calories": f"{nutrients.get('Calories', 0):.0f} kcal",
                        "protein": f"{nutrients.get('Protein', 0):.1f} g",
                        "carbs": f"{nutrients.get('Carbohydrates', 0):.1f} g",
                        "fat": f"{nutrients.get('Fat', 0):.1f} g"
                    }
                }
                recipes.append(recipe)
            except Exception as e:
                print(f"Error parsing Spoonacular recipe: {str(e)}")
                continue
        return recipes
    except Exception as e:
        print(f"Spoonacular Error: {str(e)}")
        return []

@retry(max_retries=2)
def scrape_online_recipes(query):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
        }
        # Use updated URL parameters for AllRecipes search
        search_url = f"https://www.allrecipes.com/search/results/?wt={query.replace(' ', '+')}&sort=re"
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract unique recipe links that start with the proper URL pattern
        recipe_links = list({a['href'] for a in soup.find_all('a', href=re.compile(r'^https://www.allrecipes.com/recipe/'))})
        if not recipe_links:
            print("No recipe links found on AllRecipes search page")
            print(f"HTML snippet: {soup.prettify()[:1000]}")
            all_links = [a['href'] for a in soup.find_all('a', href=True)][:10]
            print(f"Sample links found: {all_links}")
            return []

        recipes = []
        for link in recipe_links[:5]:
            try:
                recipe_page = requests.get(link, headers=headers, timeout=10)
                recipe_page.raise_for_status()
                recipe_soup = BeautifulSoup(recipe_page.text, 'html.parser')

                title_tag = recipe_soup.find('h1')
                title = title_tag.get_text(strip=True) if title_tag else "Untitled"

                # Look for ingredient elements using a regex on class names
                ingredients = [ing.get_text(strip=True).lower() for ing in recipe_soup.find_all(class_=re.compile("ingredient")) if ing.get_text(strip=True)]
                if not ingredients:
                    print(f"No ingredients found for {title}")
                    continue

                # Collect instructions from elements with "instruction" or "direction" in their class names
                instructions = []
                for instr in recipe_soup.find_all(class_=re.compile("(instruction|direction)")):
                    text = instr.get_text(strip=True)
                    if text and text not in instructions:
                        instructions.append(text)
                if not instructions:
                    instructions = ["Instructions not available"]

                # Attempt to fetch a main image
                image_tag = recipe_soup.find('img', src=re.compile("https://images.media-allrecipes.com/"))
                image = image_tag['src'] if image_tag and image_tag.get('src') else "https://example.com/placeholder.jpg"

                # Extract nutrition info if available
                nutrition = {"calories": "Unknown", "protein": "Unknown", "carbs": "Unknown", "fat": "Unknown"}
                nutrition_section = recipe_soup.find(class_=re.compile("nutrition"))
                if nutrition_section:
                    nutrition_text = nutrition_section.get_text(separator=" ", strip=True)
                    cal_match = re.search(r'(\d+)\s+calories', nutrition_text, re.IGNORECASE)
                    if cal_match:
                        nutrition['calories'] = cal_match.group(1) + " kcal"
                    protein_match = re.search(r'(\d+\.?\d*)\s+g protein', nutrition_text, re.IGNORECASE)
                    if protein_match:
                        nutrition['protein'] = protein_match.group(1) + " g"
                    carbs_match = re.search(r'(\d+\.?\d*)\s+g carbohydrates', nutrition_text, re.IGNORECASE)
                    if carbs_match:
                        nutrition['carbs'] = carbs_match.group(1) + " g"
                    fat_match = re.search(r'(\d+\.?\d*)\s+g fat', nutrition_text, re.IGNORECASE)
                    if fat_match:
                        nutrition['fat'] = fat_match.group(1) + " g"

                recipe = {
                    "title": title,
                    "image": image,
                    "ingredients": [{"name": ing, "usMeasurement": "", "metricMeasurement": ""} for ing in ingredients],
                    "instructions": instructions,
                    "timeCategory": "Medium",
                    "culturalOrigin": "International",
                    "source": "AllRecipes",
                    "nutrition": nutrition
                }
                recipes.append(recipe)
            except Exception as e:
                print(f"Error parsing scraped recipe from {link}: {str(e)}")
                continue
        return recipes
    except Exception as e:
        print(f"Scraping Error: {str(e)}")
        return []

@retry(max_retries=2)
def query_gemini_ai(query):
    try:
        prompt = (
            "You are a professional chef AI. Using ONLY these ingredients (no extras): {},\n"
            "create 5 distinct recipes with this EXACT JSON structure:\n"
            "[{\n"
            "  \"title\": \"Recipe Name\", \n"
            "  \"ingredients\": [{\"name\": \"Ingredient\", \"usMeasurement\": \"1 cup\", \"metricMeasurement\": \"240ml\"}],\n"
            "  \"instructions\": [\"Step 1\", \"Step 2\"], \n"
            "  \"timeCategory\": \"Quick/Medium/Long\", \n"
            "  \"culturalOrigin\": \"Cuisine Type\", \n"
            "  \"image\": \"https://example.com/image.jpg\", \n"
            "  \"nutrition\": {\"calories\": \"500 kcal\", \"protein\": \"20g\", \"carbs\": \"50g\", \"fat\": \"25g\"}\n"
            "}]\n"
            "Provide estimated calories, protein, carbs, and fat for each recipe. Ensure valid JSON with proper escaping."
        ).format(query)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        text = data['candidates'][0]['content']['parts'][0]['text']

        # Use regex to extract a JSON array from the response text
        match = re.search(r'(\[.*\])', text, re.DOTALL)
        if not match:
            print("No JSON array found in Gemini response")
            print(f"Raw response: {text[:500]}")
            return []
        json_text = match.group(1)
        try:
            recipes = json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")
            print(f"Cleaned JSON attempt: {json_text[:500]}")
            return []

        for recipe in recipes:
            recipe['source'] = "Gemini AI"
            recipe.setdefault('ingredients', [])
            recipe.setdefault('instructions', [])
            recipe.setdefault('image', 'https://example.com/placeholder.jpg')
            recipe.setdefault('nutrition', {"calories": "Unknown", "protein": "Unknown", "carbs": "Unknown", "fat": "Unknown"})
        return recipes
    except Exception as e:
        print(f"Gemini Error: {str(e)}")
        return []

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        ingredients = request.form.get("ingredients", "").strip()
        if not ingredients:
            return render_template("index.html", error="Please enter ingredients")

        try:
            sources = [
                ("Spoonacular", get_spoonacular_recipes),
                ("Web Scraping", scrape_online_recipes),
                ("Gemini AI", query_gemini_ai)
            ]
            all_recipes = []
            for source_name, source_func in sources:
                try:
                    recipes = source_func(ingredients)
                    all_recipes.extend(recipes)
                except Exception as e:
                    print(f"Error from {source_name}: {str(e)}")
                    continue

            if not all_recipes:
                return render_template("index.html", error="No recipes found. Try different ingredients.")
            return render_template("results.html", result={"data": all_recipes, "error": None})
        except Exception as e:
            print(f"General Error: {str(e)}")
            return render_template("index.html", error="An error occurred. Please try again.")
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
