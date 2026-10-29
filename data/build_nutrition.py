"""Builds data/food101_nutrition.csv and data/healthy_alternatives.csv.

Values are per standard serving, built from USDA-style averages for a typical
restaurant portion. Carbs are derived from kcal so the macros always add up:
    carbs_g = (kcal - 4*protein - 9*fat) / 4

Run:  python data/build_nutrition.py
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))

COLUMNS = ["food_id", "name", "category", "serving", "serving_g", "kcal",
           "protein_g", "carbs_g", "fat_g", "sat_fat_g", "fibre_g", "sugar_g",
           "sodium_mg", "tags"]

# id, name, category, serving, grams, kcal, protein, fat, sat_fat, fibre, sugar, sodium_mg, tags
FOOD101 = [
    # ---- Meat (7) ----
    ("baby_back_ribs", "Baby Back Ribs", "Meat", "half rack", 300, 887, 60, 58, 21, 1, 28, 1400, "pork,bbq,grilled,savory,smoky"),
    ("filet_mignon", "Filet Mignon", "Meat", "1 steak with butter", 250, 560, 52, 38, 16, 0, 0, 520, "beef,grilled,steak,savory"),
    ("steak", "Steak", "Meat", "1 sirloin steak", 280, 700, 62, 48, 19, 0, 0, 600, "beef,grilled,steak,savory"),
    ("prime_rib", "Prime Rib", "Meat", "1 thick slice", 300, 820, 55, 64, 27, 0, 0, 900, "beef,roasted,steak,savory"),
    ("pork_chop", "Pork Chop", "Meat", "1 chop with sides", 280, 520, 45, 30, 11, 2, 4, 700, "pork,grilled,savory"),
    ("peking_duck", "Peking Duck", "Meat", "1 plate with pancakes", 300, 690, 38, 40, 12, 2, 14, 1300, "duck,roasted,savory,wrap,asian"),
    ("chicken_curry", "Chicken Curry", "Meat", "1 bowl", 350, 560, 34, 30, 12, 4, 8, 1100, "chicken,curry,spicy,savory,saucy,asian"),
    # ---- Fast food (10) ----
    ("hamburger", "Hamburger", "Fast food", "1 burger", 250, 650, 30, 34, 12.5, 2, 8, 1150, "beef,bun,grilled,savory,cheesy,handheld,burger"),
    ("hot_dog", "Hot Dog", "Fast food", "1 hot dog", 150, 450, 16, 28, 10, 1, 6, 1250, "pork,bun,sausage,savory,handheld"),
    ("french_fries", "French Fries", "Fast food", "large portion", 170, 520, 6, 26, 4, 6, 0.5, 480, "potato,fried,salty,side,vegetarian"),
    ("pizza", "Pizza", "Fast food", "2 slices", 220, 600, 26, 24, 11, 4, 7, 1300, "bread,cheesy,baked,tomato,savory,pizza"),
    ("chicken_wings", "Chicken Wings", "Fast food", "10 wings", 300, 720, 54, 50, 14, 0, 6, 2100, "chicken,fried,spicy,savory"),
    ("nachos", "Nachos", "Fast food", "1 plate", 300, 780, 24, 46, 17, 9, 4, 1300, "tortilla,cheesy,fried,beef,spicy,mexican,savory"),
    ("poutine", "Poutine", "Fast food", "1 box", 350, 740, 22, 44, 18, 6, 2, 1600, "potato,fried,cheesy,gravy,savory"),
    ("onion_rings", "Onion Rings", "Fast food", "1 portion", 150, 480, 6, 28, 5, 3, 6, 700, "onion,fried,side,salty,vegetarian"),
    ("chicken_quesadilla", "Chicken Quesadilla", "Fast food", "1 quesadilla", 280, 680, 38, 36, 17, 3, 3, 1450, "chicken,tortilla,cheesy,mexican,handheld,savory"),
    ("tacos", "Tacos", "Fast food", "3 tacos", 300, 620, 30, 32, 12, 6, 3, 1100, "beef,tortilla,mexican,spicy,handheld,savory"),
    # ---- Pasta (6) ----
    ("lasagna", "Lasagna", "Pasta", "1 large piece", 350, 680, 36, 34, 17, 5, 10, 1250, "beef,pasta,cheesy,baked,tomato,italian"),
    ("macaroni_and_cheese", "Macaroni and Cheese", "Pasta", "1 bowl", 300, 640, 24, 32, 18, 3, 7, 1100, "pasta,cheesy,creamy,baked,vegetarian"),
    ("spaghetti_bolognese", "Spaghetti Bolognese", "Pasta", "1 plate", 400, 620, 30, 20, 7, 7, 12, 900, "beef,pasta,tomato,italian,saucy"),
    ("spaghetti_carbonara", "Spaghetti Carbonara", "Pasta", "1 plate", 350, 720, 30, 34, 14, 3, 3, 1100, "pork,egg,pasta,creamy,cheesy,italian"),
    ("ravioli", "Ravioli", "Pasta", "1 plate", 300, 520, 22, 22, 11, 4, 8, 950, "pasta,cheesy,tomato,italian,vegetarian"),
    ("gnocchi", "Gnocchi", "Pasta", "1 plate", 300, 552, 14, 22, 12, 4, 4, 850, "potato,pasta,creamy,cheesy,italian,vegetarian"),
    # ---- Rice & noodles (7) ----
    ("bibimbap", "Bibimbap", "Rice & noodles", "1 bowl", 450, 590, 26, 18, 4, 6, 10, 1050, "rice,beef,egg,vegetable,bowl,spicy,asian"),
    ("fried_rice", "Fried Rice", "Rice & noodles", "1 plate", 350, 640, 20, 24, 5, 3, 4, 1400, "rice,egg,fried,asian,savory"),
    ("pad_thai", "Pad Thai", "Rice & noodles", "1 plate", 380, 680, 28, 26, 5, 4, 18, 1500, "noodle,shrimp,egg,peanut,asian,savory"),
    ("paella", "Paella", "Rice & noodles", "1 plate", 400, 620, 34, 20, 4, 4, 3, 1100, "rice,seafood,chicken,spanish,savory"),
    ("ramen", "Ramen", "Rice & noodles", "1 bowl", 550, 560, 26, 22, 7, 3, 4, 2200, "noodle,pork,egg,soup,asian,salty"),
    ("pho", "Pho", "Rice & noodles", "1 bowl", 600, 450, 30, 10, 3, 2, 6, 1800, "noodle,beef,soup,asian"),
    ("risotto", "Risotto", "Rice & noodles", "1 plate", 350, 660, 18, 26, 13, 2, 3, 1000, "rice,creamy,cheesy,italian,vegetarian"),
    # ---- Sandwich (5) ----
    ("club_sandwich", "Club Sandwich", "Sandwich", "1 sandwich", 300, 620, 36, 32, 9, 4, 7, 1600, "chicken,pork,bread,handheld,savory"),
    ("grilled_cheese_sandwich", "Grilled Cheese Sandwich", "Sandwich", "1 sandwich", 180, 520, 20, 30, 16, 2, 5, 1100, "bread,cheesy,grilled,handheld,vegetarian"),
    ("croque_madame", "Croque Madame", "Sandwich", "1 sandwich", 280, 650, 34, 36, 18, 2, 5, 1700, "pork,egg,bread,cheesy,baked,handheld"),
    ("lobster_roll_sandwich", "Lobster Roll Sandwich", "Sandwich", "1 roll", 200, 475, 26, 22, 6, 1, 5, 1050, "seafood,bun,handheld,creamy"),
    ("pulled_pork_sandwich", "Pulled Pork Sandwich", "Sandwich", "1 sandwich", 280, 600, 34, 22, 7, 2, 22, 1300, "pork,bun,bbq,handheld,smoky"),
    # ---- Breakfast (7) ----
    ("eggs_benedict", "Eggs Benedict", "Breakfast", "2 halves", 300, 720, 30, 50, 22, 2, 3, 1500, "egg,pork,bread,creamy,breakfast"),
    ("pancakes", "Pancakes", "Breakfast", "3 pancakes with syrup", 250, 520, 12, 16, 6, 2, 28, 900, "pancake,sweet,breakfast,syrup,vegetarian"),
    ("waffles", "Waffles", "Breakfast", "2 waffles with syrup", 220, 560, 12, 24, 10, 2, 26, 850, "waffle,sweet,breakfast,syrup,vegetarian"),
    ("french_toast", "French Toast", "Breakfast", "3 slices with syrup", 230, 540, 16, 22, 8, 2, 24, 650, "bread,egg,sweet,breakfast,syrup,vegetarian"),
    ("omelette", "Omelette", "Breakfast", "3-egg cheese omelette", 220, 380, 24, 28, 11, 1, 3, 650, "egg,cheesy,breakfast,vegetarian,savory"),
    ("huevos_rancheros", "Huevos Rancheros", "Breakfast", "1 plate", 350, 560, 24, 30, 10, 9, 6, 1200, "egg,tortilla,bean,mexican,spicy,breakfast,vegetarian"),
    ("breakfast_burrito", "Breakfast Burrito", "Breakfast", "1 burrito", 280, 528, 26, 26, 10, 4, 3, 1200, "egg,pork,tortilla,cheesy,breakfast,handheld,mexican"),
    # ---- Dessert (20) ----
    ("apple_pie", "Apple Pie", "Dessert", "1 slice", 150, 410, 4, 19, 9, 2, 26, 330, "pastry,fruit,apple,baked,sweet"),
    ("baklava", "Baklava", "Dessert", "2 pieces", 80, 330, 5, 20, 7, 2, 20, 200, "pastry,nut,honey,sweet"),
    ("beignets", "Beignets", "Dessert", "3 beignets", 100, 390, 6, 20, 5, 1, 18, 300, "fried,dough,sweet,pastry"),
    ("bread_pudding", "Bread Pudding", "Dessert", "1 bowl", 180, 420, 9, 16, 8, 1, 34, 350, "bread,creamy,baked,sweet"),
    ("cannoli", "Cannoli", "Dessert", "2 cannoli", 110, 360, 9, 20, 9, 1, 22, 150, "pastry,cheese,creamy,sweet,italian"),
    ("carrot_cake", "Carrot Cake", "Dessert", "1 slice", 150, 490, 5, 28, 6, 2, 40, 380, "cake,baked,creamy,sweet"),
    ("cheesecake", "Cheesecake", "Dessert", "1 slice", 140, 480, 8, 32, 18, 1, 30, 380, "cake,cheese,creamy,sweet"),
    ("chocolate_cake", "Chocolate Cake", "Dessert", "1 slice", 150, 520, 6, 26, 10, 4, 48, 420, "cake,chocolate,baked,sweet"),
    ("chocolate_mousse", "Chocolate Mousse", "Dessert", "1 cup", 120, 350, 6, 26, 15, 2, 22, 60, "chocolate,creamy,sweet"),
    ("churros", "Churros", "Dessert", "4 churros", 100, 380, 4, 20, 4, 2, 18, 300, "fried,dough,sweet,cinnamon"),
    ("creme_brulee", "Creme Brulee", "Dessert", "1 ramekin", 130, 340, 5, 24, 14, 0, 26, 60, "custard,creamy,sweet,egg"),
    ("cup_cakes", "Cupcakes", "Dessert", "1 frosted cupcake", 90, 330, 3, 15, 6, 1, 32, 250, "cake,baked,sweet"),
    ("donuts", "Donuts", "Dessert", "1 glazed donut", 75, 300, 4, 16, 7, 1, 16, 280, "fried,dough,sweet"),
    ("frozen_yogurt", "Frozen Yogurt", "Dessert", "1 cup", 200, 230, 6, 4, 2.5, 0, 34, 120, "yogurt,frozen,creamy,sweet"),
    ("ice_cream", "Ice Cream", "Dessert", "2 scoops", 130, 280, 5, 15, 9, 1, 28, 100, "frozen,creamy,sweet"),
    ("macarons", "Macarons", "Dessert", "4 macarons", 70, 290, 5, 13, 3, 2, 34, 40, "almond,cookie,sweet"),
    ("panna_cotta", "Panna Cotta", "Dessert", "1 cup", 140, 330, 4, 24, 15, 0, 22, 50, "creamy,custard,sweet,italian"),
    ("red_velvet_cake", "Red Velvet Cake", "Dessert", "1 slice", 140, 490, 5, 24, 7, 1, 46, 400, "cake,creamy,baked,sweet"),
    ("strawberry_shortcake", "Strawberry Shortcake", "Dessert", "1 piece", 160, 380, 5, 18, 10, 2, 30, 300, "cake,fruit,strawberry,creamy,sweet"),
    ("tiramisu", "Tiramisu", "Dessert", "1 piece", 150, 460, 8, 28, 16, 1, 30, 120, "cake,creamy,coffee,sweet,italian"),
    # ---- Soup (5) ----
    ("clam_chowder", "Clam Chowder", "Soup", "1 bowl", 350, 470, 18, 28, 14, 2, 6, 1300, "seafood,creamy,soup,potato"),
    ("french_onion_soup", "French Onion Soup", "Soup", "1 bowl", 350, 500, 20, 26, 14, 3, 10, 1600, "onion,cheesy,soup,bread,vegetarian"),
    ("hot_and_sour_soup", "Hot and Sour Soup", "Soup", "1 bowl", 350, 220, 12, 8, 2, 2, 4, 1600, "tofu,soup,spicy,asian"),
    ("lobster_bisque", "Lobster Bisque", "Soup", "1 bowl", 300, 530, 16, 38, 22, 1, 6, 1200, "seafood,creamy,soup"),
    ("miso_soup", "Miso Soup", "Soup", "1 bowl", 250, 110, 7, 4, 0.6, 2, 3, 900, "tofu,soup,asian,vegetarian"),
    # ---- Snack (8) ----
    ("edamame", "Edamame", "Snack", "1 bowl", 155, 190, 17, 8, 1, 8, 3, 400, "bean,legume,salty,vegetarian,asian"),
    ("falafel", "Falafel", "Snack", "5 pieces", 150, 420, 14, 24, 3, 8, 2, 700, "legume,fried,vegetarian,middle_eastern"),
    ("garlic_bread", "Garlic Bread", "Snack", "3 slices", 110, 380, 8, 20, 9, 2, 2, 600, "bread,garlic,baked,vegetarian,side"),
    ("samosa", "Samosa", "Snack", "2 samosas", 160, 460, 8, 26, 5, 5, 3, 650, "pastry,fried,potato,spicy,vegetarian"),
    ("spring_rolls", "Spring Rolls", "Snack", "3 rolls", 150, 330, 8, 16, 3, 3, 4, 700, "fried,vegetable,pastry,asian,handheld"),
    ("takoyaki", "Takoyaki", "Snack", "6 balls", 180, 380, 14, 18, 4, 2, 8, 900, "seafood,fried,asian,savory"),
    ("hummus", "Hummus", "Snack", "1 bowl with pita", 150, 290, 10, 16, 2, 7, 1, 500, "legume,dip,vegetarian,middle_eastern"),
    ("guacamole", "Guacamole", "Snack", "1 bowl", 150, 270, 4, 20, 3, 10, 2, 450, "avocado,dip,vegetarian,mexican"),
    # ---- Seafood (10) ----
    ("grilled_salmon", "Grilled Salmon", "Seafood", "1 fillet", 180, 370, 38, 22, 4, 0, 0, 400, "fish,grilled,savory"),
    ("fish_and_chips", "Fish and Chips", "Seafood", "1 portion", 350, 720, 32, 38, 8, 5, 2, 1100, "fish,fried,potato,savory"),
    ("sashimi", "Sashimi", "Seafood", "10 slices", 200, 180, 30, 6, 1, 0, 0, 300, "fish,raw,asian"),
    ("sushi", "Sushi", "Seafood", "6 pieces", 200, 300, 14, 6, 1, 2, 8, 700, "fish,rice,raw,asian"),
    ("scallops", "Scallops", "Seafood", "5 seared scallops", 150, 220, 24, 10, 3, 0, 0, 600, "seafood,seared,savory"),
    ("mussels", "Mussels", "Seafood", "1 pot (meat)", 200, 280, 28, 10, 4, 0, 1, 900, "seafood,savory,saucy"),
    ("oysters", "Oysters", "Seafood", "6 oysters", 140, 120, 12, 4, 1, 0, 0, 300, "seafood,raw"),
    ("shrimp_and_grits", "Shrimp and Grits", "Seafood", "1 bowl", 350, 480, 28, 24, 11, 2, 2, 1200, "seafood,shrimp,creamy,cheesy,savory"),
    ("tuna_tartare", "Tuna Tartare", "Seafood", "1 portion", 150, 250, 26, 12, 2, 1, 3, 600, "fish,raw,avocado"),
    ("ceviche", "Ceviche", "Seafood", "1 bowl", 200, 200, 24, 3, 0.5, 2, 4, 500, "fish,raw,citrus,latin"),
    # ---- Appetizer (11) ----
    ("beef_carpaccio", "Beef Carpaccio", "Appetizer", "1 plate", 100, 220, 18, 15, 4, 0, 1, 450, "beef,raw,italian"),
    ("beef_tartare", "Beef Tartare", "Appetizer", "1 portion", 130, 300, 24, 21, 7, 0, 1, 500, "beef,raw,egg"),
    ("bruschetta", "Bruschetta", "Appetizer", "3 pieces", 120, 260, 6, 10, 1.5, 3, 4, 450, "bread,tomato,italian,vegetarian"),
    ("cheese_plate", "Cheese Plate", "Appetizer", "1 small board", 100, 380, 22, 30, 18, 1, 2, 700, "cheese,vegetarian,savory"),
    ("deviled_eggs", "Deviled Eggs", "Appetizer", "4 halves", 110, 210, 12, 17, 4, 0, 1, 350, "egg,creamy,vegetarian"),
    ("dumplings", "Dumplings", "Appetizer", "6 pieces", 180, 300, 14, 12, 4, 2, 3, 800, "pork,dough,steamed,asian"),
    ("escargots", "Escargots", "Appetizer", "6 snails in butter", 90, 270, 14, 22, 12, 0, 0, 450, "garlic,buttery,french"),
    ("foie_gras", "Foie Gras", "Appetizer", "1 portion with toast", 80, 360, 8, 34, 13, 0, 2, 500, "duck,rich,french"),
    ("gyoza", "Gyoza", "Appetizer", "6 pieces", 150, 300, 12, 14, 4, 2, 2, 750, "pork,dough,fried,asian"),
    ("crab_cakes", "Crab Cakes", "Appetizer", "2 cakes", 140, 320, 18, 18, 4, 1, 2, 800, "seafood,fried,savory"),
    ("fried_calamari", "Fried Calamari", "Appetizer", "1 plate", 150, 360, 18, 20, 3, 1, 1, 700, "seafood,fried,savory"),
    # ---- Salad (5) ----
    ("beet_salad", "Beet Salad", "Salad", "1 bowl", 250, 250, 7, 16, 4, 5, 14, 400, "salad,vegetable,cheese,vegetarian"),
    ("caesar_salad", "Caesar Salad", "Salad", "1 bowl", 250, 360, 14, 28, 6, 4, 3, 800, "salad,cheesy,creamy,bread"),
    ("caprese_salad", "Caprese Salad", "Salad", "1 plate", 220, 300, 16, 24, 10, 1, 4, 350, "salad,cheese,tomato,italian,vegetarian"),
    ("greek_salad", "Greek Salad", "Salad", "1 bowl", 280, 280, 8, 22, 7, 4, 7, 900, "salad,cheese,vegetable,vegetarian"),
    ("seaweed_salad", "Seaweed Salad", "Salad", "1 bowl", 150, 200, 3, 10, 1.5, 6, 12, 900, "salad,seaweed,asian,vegetarian"),
]

ALTERNATIVES = [
    ("turkey_burger_lettuce_wrap", "Turkey Burger in Lettuce Wrap", "Fast food", "1 burger", 220, 290, 28, 14, 3, 3, 4, 600, "turkey,grilled,savory,handheld,burger,wrap"),
    ("turkey_hot_dog_ww_bun", "Turkey Hot Dog, Whole-Wheat Bun", "Fast food", "1 hot dog", 140, 260, 14, 10, 2, 4, 5, 900, "turkey,bun,sausage,savory,handheld,whole_grain"),
    ("grilled_chicken_breast_veg", "Grilled Chicken Breast with Steamed Veg", "Meat", "1 plate", 350, 350, 42, 12, 2, 9, 6, 450, "chicken,grilled,vegetable,savory"),
    ("turkey_avocado_sandwich", "Turkey & Avocado Sandwich", "Sandwich", "1 sandwich", 250, 390, 28, 14, 3, 8, 5, 850, "turkey,bread,avocado,handheld,whole_grain,savory"),
    ("thin_crust_veggie_pizza", "Thin-Crust Veggie Pizza", "Fast food", "2 slices", 170, 360, 16, 13, 5, 5, 6, 720, "bread,cheesy,baked,tomato,vegetable,vegetarian,pizza,savory"),
    ("air_fried_potato_wedges", "Air-Fried Potato Wedges", "Snack", "1 serving", 150, 190, 4, 4, 1, 4, 1, 200, "potato,baked,side,salty,vegetarian"),
    ("roasted_pork_tenderloin_veg", "Roasted Pork Tenderloin & Veggies", "Meat", "1 plate", 350, 380, 42, 13, 4, 6, 9, 420, "pork,roasted,vegetable,savory"),
    ("grilled_chicken_wrap", "Grilled Chicken Wrap", "Sandwich", "1 wrap", 250, 380, 30, 10, 3, 5, 3, 750, "chicken,tortilla,grilled,handheld,wrap,savory"),
    ("baked_chicken_wings", "Baked Chicken Wings", "Fast food", "8 wings", 220, 330, 40, 18, 5, 0, 2, 700, "chicken,baked,spicy,savory"),
    ("bean_veggie_tacos", "Bean & Veggie Tacos", "Fast food", "3 tacos", 300, 380, 14, 10, 3, 12, 4, 600, "bean,tortilla,mexican,vegetable,handheld,vegetarian,spicy"),
    ("chicken_fajita_bowl", "Chicken Fajita Bowl", "Rice & noodles", "1 bowl", 400, 450, 36, 12, 3, 9, 6, 800, "chicken,rice,mexican,vegetable,bowl,spicy"),
    ("baked_tortilla_chips_salsa", "Baked Tortilla Chips & Salsa", "Snack", "1 bowl", 100, 220, 5, 6, 1, 5, 3, 380, "tortilla,baked,mexican,salty,tomato,vegetarian"),
    ("lean_sirloin_salad", "Lean Sirloin Salad", "Salad", "1 bowl", 350, 400, 34, 16, 5, 5, 6, 450, "beef,grilled,steak,salad,vegetable"),
    ("grilled_sirloin_veg", "Grilled Lean Sirloin & Veg", "Meat", "1 plate", 330, 420, 46, 18, 6, 6, 5, 400, "beef,grilled,steak,vegetable,savory"),
    ("chicken_tikka_cauli_rice", "Chicken Tikka with Cauliflower Rice", "Meat", "1 bowl", 380, 380, 38, 14, 4, 7, 8, 850, "chicken,curry,spicy,asian,vegetable,saucy"),
    ("roast_turkey_breast_veg", "Roast Turkey Breast & Veg", "Meat", "1 plate", 330, 330, 44, 8, 2, 6, 7, 500, "turkey,roasted,vegetable,savory"),
    ("ww_spaghetti_turkey_bolognese", "Whole-Wheat Spaghetti, Turkey Bolognese", "Pasta", "1 plate", 380, 480, 34, 10, 3, 10, 10, 600, "turkey,pasta,tomato,italian,whole_grain,saucy"),
    ("zucchini_noodles_marinara", "Zucchini Noodles Marinara", "Pasta", "1 bowl", 350, 220, 8, 9, 2, 6, 12, 500, "vegetable,tomato,italian,vegetarian,pasta"),
    ("veggie_lasagna_light", "Light Veggie Lasagna", "Pasta", "1 piece", 300, 380, 22, 12, 6, 7, 9, 700, "pasta,vegetable,cheesy,baked,tomato,italian,vegetarian"),
    ("ww_mac_cauliflower", "Whole-Wheat Mac & Cauliflower Cheese", "Pasta", "1 bowl", 280, 360, 18, 12, 6, 7, 6, 600, "pasta,cheesy,creamy,vegetable,whole_grain,vegetarian"),
    ("lemon_chicken_pasta", "Lemon Chicken Whole-Wheat Pasta", "Pasta", "1 plate", 350, 470, 34, 11, 3, 6, 4, 550, "chicken,pasta,italian,whole_grain"),
    ("brown_rice_veggie_stir_fry", "Brown Rice Tofu Stir-Fry", "Rice & noodles", "1 bowl", 400, 420, 14, 10, 2, 8, 8, 700, "rice,vegetable,tofu,asian,whole_grain,vegetarian"),
    ("cauliflower_fried_rice", "Cauliflower Fried Rice", "Rice & noodles", "1 bowl", 300, 240, 14, 10, 2, 6, 6, 650, "rice,vegetable,egg,asian,vegetarian"),
    ("salmon_poke_bowl", "Salmon Poke Bowl", "Rice & noodles", "1 bowl", 400, 480, 32, 14, 3, 6, 8, 900, "fish,rice,raw,bowl,asian"),
    ("soba_noodle_veg", "Soba Noodles with Veg & Tofu", "Rice & noodles", "1 bowl", 350, 340, 16, 6, 1, 6, 6, 800, "noodle,vegetable,tofu,asian,vegetarian"),
    ("chicken_garden_salad", "Grilled Chicken Garden Salad, Light Dressing", "Salad", "1 bowl", 320, 250, 30, 8, 2, 6, 6, 450, "salad,chicken,grilled,vegetable,cheese,tomato"),
    ("shrimp_zucchini_pad_thai", "Shrimp Zucchini Pad Thai", "Rice & noodles", "1 plate", 350, 360, 28, 14, 2, 6, 10, 900, "noodle,shrimp,peanut,asian,vegetable"),
    ("veggie_egg_white_omelette", "Veggie Egg-White Omelette", "Breakfast", "1 omelette", 250, 200, 22, 7, 2, 4, 4, 450, "egg,vegetable,breakfast,vegetarian,savory"),
    ("oat_banana_pancakes", "Oat & Banana Pancakes", "Breakfast", "3 pancakes", 200, 320, 14, 8, 2, 6, 12, 300, "pancake,oat,fruit,breakfast,sweet,vegetarian"),
    ("whole_grain_waffle_berries", "Whole-Grain Waffle with Berries", "Breakfast", "1 waffle", 180, 300, 10, 8, 2, 6, 12, 400, "waffle,fruit,whole_grain,breakfast,sweet,vegetarian"),
    ("avocado_toast_egg", "Avocado Toast with Egg", "Breakfast", "2 slices", 220, 370, 15, 18, 4, 9, 3, 450, "bread,avocado,egg,whole_grain,breakfast,vegetarian,savory"),
    ("egg_veggie_breakfast_wrap", "Egg & Veggie Breakfast Wrap", "Breakfast", "1 wrap", 220, 320, 20, 12, 4, 6, 3, 650, "egg,tortilla,vegetable,breakfast,handheld,vegetarian,mexican"),
    ("greek_yogurt_parfait", "Greek Yogurt Parfait", "Dessert", "1 cup", 220, 220, 16, 4, 2, 4, 18, 80, "yogurt,fruit,creamy,sweet,breakfast"),
    ("fresh_fruit_salad", "Fresh Fruit Salad", "Dessert", "1 bowl", 250, 120, 2, 0.5, 0, 5, 22, 10, "fruit,sweet,fresh,vegetarian"),
    ("baked_cinnamon_apple", "Baked Cinnamon Apple", "Dessert", "1 apple", 200, 150, 1, 2, 1, 5, 26, 10, "fruit,apple,baked,cinnamon,sweet,vegetarian"),
    ("dark_chocolate_strawberries", "Dark Chocolate Strawberries", "Dessert", "6 berries", 150, 180, 3, 9, 5, 5, 18, 10, "chocolate,fruit,strawberry,sweet,vegetarian"),
    ("chia_pudding", "Chia Pudding", "Dessert", "1 cup", 180, 200, 7, 9, 1.5, 10, 10, 60, "creamy,pudding,custard,sweet,vegetarian"),
    ("banana_nice_cream", "Banana Nice Cream", "Dessert", "1 cup", 160, 150, 2, 1, 0.3, 4, 20, 5, "frozen,creamy,fruit,sweet,vegetarian"),
    ("citrus_shrimp_salad", "Citrus Shrimp Salad", "Salad", "1 bowl", 280, 210, 24, 7, 1, 4, 6, 500, "salad,shrimp,seafood,citrus,vegetable"),
    ("angel_food_cake_berries", "Angel Food Cake with Berries", "Dessert", "1 slice", 120, 200, 5, 1, 0, 3, 30, 300, "cake,fruit,baked,sweet,strawberry"),
    ("light_ricotta_cheesecake_cup", "Light Ricotta Cheesecake Cup", "Dessert", "1 cup", 130, 220, 12, 8, 5, 1, 18, 180, "cheese,creamy,cake,sweet"),
    ("cocoa_avocado_mousse", "Cocoa Avocado Mousse", "Dessert", "1 cup", 130, 210, 4, 14, 3, 7, 12, 30, "chocolate,creamy,avocado,sweet,vegetarian"),
    ("oat_date_energy_bites", "Oat & Date Energy Bites", "Dessert", "3 bites", 60, 180, 5, 8, 2, 4, 16, 20, "oat,nut,sweet,vegetarian,dough"),
    ("grilled_fish_tacos", "Grilled Fish Tacos", "Seafood", "2 tacos", 250, 330, 26, 10, 2, 6, 3, 600, "fish,tortilla,grilled,mexican,handheld"),
    ("baked_cod_sweet_potato", "Baked Cod & Sweet Potato", "Seafood", "1 plate", 350, 340, 30, 6, 1, 6, 8, 400, "fish,baked,potato,savory"),
    ("shrimp_veggie_skewers", "Shrimp & Veggie Skewers", "Seafood", "2 skewers", 220, 220, 26, 7, 1, 3, 5, 650, "seafood,shrimp,grilled,vegetable,savory"),
    ("lentil_vegetable_soup", "Lentil Vegetable Soup", "Soup", "1 bowl", 400, 230, 14, 4, 0.5, 12, 6, 650, "legume,soup,vegetable,vegetarian"),
    ("tomato_basil_soup_light", "Light Tomato Basil Soup", "Soup", "1 bowl", 350, 140, 4, 4, 1, 4, 10, 550, "tomato,soup,vegetarian,creamy"),
    ("steamed_chicken_veg_dumplings", "Steamed Chicken & Veg Dumplings", "Appetizer", "6 pieces", 180, 220, 16, 5, 1, 3, 3, 550, "chicken,dough,steamed,asian,vegetable"),
    ("hummus_veggie_sticks", "Hummus with Veggie Sticks", "Snack", "1 plate", 200, 160, 6, 8, 1, 7, 4, 300, "legume,dip,vegetable,vegetarian,middle_eastern"),
]


def to_rows(items):
    rows = []
    for fid, name, cat, serving, g, kcal, p, f, sat, fib, sug, na, tags in items:
        carbs = round((kcal - 4 * p - 9 * f) / 4, 1)
        assert carbs >= 0, f"{fid}: negative carbs ({carbs})"
        assert sat <= f, f"{fid}: sat fat > fat"
        rows.append({
            "food_id": fid, "name": name, "category": cat, "serving": serving,
            "serving_g": g, "kcal": kcal, "protein_g": p, "carbs_g": carbs,
            "fat_g": f, "sat_fat_g": sat, "fibre_g": fib, "sugar_g": sug,
            "sodium_mg": na, "tags": tags,
        })
    return rows


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    foods, alts = to_rows(FOOD101), to_rows(ALTERNATIVES)
    assert len(foods) == 101 and len({r["food_id"] for r in foods}) == 101
    assert len(alts) == 50 and len({r["food_id"] for r in alts}) == 50
    write(os.path.join(HERE, "food101_nutrition.csv"), foods)
    write(os.path.join(HERE, "healthy_alternatives.csv"), alts)
    print(f"wrote {len(foods)} foods and {len(alts)} alternatives")
