from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# Replace with your Spoonacular API key
SPOONACULAR_API_KEY = "26f3770f6bcd4258a019e530d42538ae"


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search():
    ingredients = request.form.get('ingredients')
    if not ingredients:
        return "Please enter ingredients."

    # Search recipes based on provided ingredients
    url = f"https://api.spoonacular.com/recipes/findByIngredients?ingredients={ingredients}&number=5&apiKey={SPOONACULAR_API_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        return "Error fetching recipes. Try again."

    recipes = response.json()
    detailed_recipes = []

    for recipe in recipes:
        recipe_id = recipe['id']
        # Get detailed recipe information with nutrition included
        info_url = f"https://api.spoonacular.com/recipes/{recipe_id}/information?includeNutrition=true&apiKey={SPOONACULAR_API_KEY}"
        info_response = requests.get(info_url)
        if info_response.status_code == 200:
            details = info_response.json()

            # Process ingredients list
            ingredients_list = [
                ing.get("original", ing.get("name", ""))
                for ing in details.get("extendedIngredients", [])
            ]

            # Process instructions into bullet points
            instructions_html = details.get("instructions", "")
            instructions_text = BeautifulSoup(instructions_html, "html.parser").get_text().strip()
            if instructions_text:
                instructions_list = [step.strip() for step in instructions_text.split('.') if step.strip()]
            else:
                instructions_list = ["No instructions available."]

            # Extract nutrition info for Calories, Fat, Carbohydrates, Protein
            nutrients_needed = {"Calories": None, "Fat": None, "Carbohydrates": None, "Protein": None}
            if details.get("nutrition"):
                for nutrient in details["nutrition"].get("nutrients", []):
                    if nutrient["name"] in nutrients_needed:
                        nutrients_needed[nutrient["name"]] = f"{nutrient['amount']} {nutrient['unit']}"

            detailed_recipes.append({
                "title": details.get("title"),
                "image": details.get("image"),
                "ingredients": ingredients_list,
                "instructions": instructions_list,
                "nutrition": nutrients_needed
            })

    return render_template('results.html', recipes=detailed_recipes)


if __name__ == '__main__':
    app.run(debug=True)
