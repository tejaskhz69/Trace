I have already built an AI food and activity tracking app. The application is working, but the nutrition and food database is not yet as comprehensive as established apps such as MyFitnessPal, MacroFactor, Cronometer, and similar platforms.

Your task is to improve the existing nutrition system without unnecessarily changing or breaking the rest of the application.

## Main objective

Make the food database universal and useful for people worldwide.

It must provide strong coverage for:

1. Indian household foods and regional dishes.
2. Indian packaged foods and brands.
3. US, Canadian, UK, European, Australian, Middle Eastern, Asian, and African foods.
4. International supermarket products.
5. Restaurant and fast-food items.
6. Generic ingredients and homemade recipes.
7. Barcode-based packaged-food lookup.
8. Multiple languages, spelling variations, and regional food names.

For example, the database should support products such as:

- Kirkland maple syrup.
- Kirkland protein bars.
- Costco products.
- US supermarket products.
- Indian brands such as Amul, Britannia, Haldiram’s, Parle, Tata, MTR, Mother Dairy, and similar products.
- UK, European, Australian, Middle Eastern, and Asian packaged foods.
- Regional Indian dishes such as dosa, idli, sambar, rajma chawal, biryani, poha, dhokla, litti chokha, appam, dal baati, and many others.

Do not assume that one country’s food database is sufficient.

## First inspect the existing app

Before writing code:

1. Inspect the complete project structure.
2. Identify the frontend, backend, database, authentication, and API systems.
3. Find all existing food, nutrition, recipe, search, barcode, and AI-related files.
4. Identify the current food data source or API.
5. Check the existing database schema.
6. Check how food search results are displayed.
7. Check how serving sizes and nutrients are calculated.
8. Find gaps, duplicate logic, broken integrations, and missing nutrition fields.

Do not rebuild the application from scratch.

Do not make major changes until you explain the current system and propose a plan.

## Required food categories

The improved database should support:

### Packaged products

Store:

- Product name.
- Brand.
- Country.
- Region.
- Barcode or GTIN.
- Product category.
- Serving size.
- Serving unit.
- Nutrients per serving.
- Nutrients per 100 g or 100 ml.
- Ingredients.
- Allergens.
- Dietary labels.
- Product image.
- Source.
- Data freshness.
- Verification status.

### Generic foods

Store:

- Raw and cooked versions.
- Calories.
- Protein.
- Carbohydrates.
- Fat.
- Fibre.
- Sugar.
- Saturated fat.
- Sodium.
- Cholesterol.
- Vitamins and minerals when available.
- Common serving units.
- Country or regional origin.

### Recipes

Store:

- Canonical dish name.
- Alternative names.
- Country.
- Region or state.
- Cuisine.
- Ingredients.
- Ingredient quantities.
- Cooking method.
- Oil, butter, ghee, or sauce quantity.
- Number of servings.
- Nutrition per recipe.
- Nutrition per serving.
- Nutrition per 100 g.
- Recipe source.
- Confidence score.

The same dish must support different regional and household variations. For example, store Tamil-style sambar, Karnataka-style sambar, restaurant sambar, and a user’s personal sambar recipe as separate variants.

## Worldwide data strategy

Design a multi-source nutrition system instead of depending on a single API.

Evaluate the existing system and recommend suitable sources for:

- Worldwide packaged foods and barcodes.
- US branded foods.
- Indian ingredients and dishes.
- European products.
- Restaurant nutrition.
- Generic ingredients.
- User-created recipes.

Use a source-priority system:

1. Official or laboratory-verified data.
2. Government nutrition databases.
3. Licensed commercial food databases.
4. Verified product-label data.
5. Dietitian-reviewed recipes.
6. Verified community submissions.
7. AI-generated estimates, clearly marked as estimates.

Before integrating any external API or dataset, check its licence, commercial-use restrictions, attribution requirements, API limits, and data quality.

Do not scrape websites or import datasets unless their terms permit it.

## Global search requirements

Improve food search so users can search using:

- Brand name.
- Product name.
- Barcode.
- Country.
- Cuisine.
- Region.
- Ingredient.
- Recipe name.
- Common spelling variations.
- Local-language names.
- Transliteration.
- Misspellings.
- Imperial and metric measurements.

Examples:

- “Kirkland protein bar.”
- “Costco maple syrup.”
- “Amul paneer.”
- “kanda poha.”
- “avalakki.”
- “पोहे.”
- “dosa.”
- “dosai.”
- “தோசை.”
- “sambar.”
- “sambhar.”
- “சாம்பார்.”

Search results should rank exact brand and product matches first, followed by regional matches, generic foods, and AI estimates.

## Nutrition accuracy requirements

Do not allow the AI to confidently invent exact nutritional values.

Every food or recipe should have:

- Data source.
- Last updated date.
- Verification status.
- Confidence score.
- Country or market.
- Serving-size basis.

For recipes, calculate nutrition from the ingredients and quantities.

Use this calculation:

Total recipe nutrition =
sum of each ingredient’s nutrition based on its quantity.

Per-serving nutrition =
total recipe nutrition divided by the number of servings.

Handle cooking yield properly for foods such as:

- Rice.
- Pasta.
- Dal.
- Beans.
- Meat.
- Vegetables.
- Noodles.

Keep raw and cooked food entries separate where necessary.

Oil, ghee, butter, sauces, dressings, and toppings must be tracked separately because they can significantly change total calories.

## User contribution system

Add or improve the ability for users to submit missing foods.

A submission should support:

- Product or recipe name.
- Brand.
- Country.
- Barcode.
- Product-label photos.
- Nutrition-label photos.
- Ingredient list.
- Serving size.
- Recipe ingredients.
- Preparation method.
- Number of servings.

Use OCR to read nutrition labels, but require user confirmation before saving the result.

Add moderation features:

- Duplicate detection.
- Community corrections.
- User reports.
- Admin approval.
- Verification status.
- Source tracking.
- Version history.

## Database design

Review the existing schema and extend it only where necessary.

The system should be able to represent:

- Ingredients.
- Packaged products.
- Brands.
- Countries.
- Cuisines.
- Regions.
- Dishes.
- Recipe variants.
- Ingredients inside recipes.
- Food aliases.
- Serving units.
- Nutrition values.
- Barcodes.
- Data sources.
- User submissions.
- Reviews and corrections.

Avoid storing all nutrition information in one unstructured table if that makes recipes, products, and serving sizes difficult to manage.

## AI capabilities

Use AI for:

- Food-name normalization.
- Multilingual alias generation.
- Ingredient matching.
- Duplicate detection.
- Nutrition-label OCR.
- Recipe parsing.
- Image-based food suggestions.
- Search suggestions.
- Regional dish classification.

AI should provide candidate results and estimates, but verified database data should be preferred whenever available.

For image-based food recognition, show uncertainty and let users correct:

- Food name.
- Ingredients.
- Portion size.
- Cooking method.
- Oil quantity.

## Implementation process

Follow this sequence:

### Phase 1: Audit

Inspect the existing application and produce:

- Current architecture summary.
- Existing nutrition flow.
- Current API and database analysis.
- Missing features.
- Data-quality problems.
- Security concerns.
- Recommended improvements.

### Phase 2: Plan

Create a practical implementation plan that preserves the working application.

Divide the work into:

- Database changes.
- API integrations.
- Search improvements.
- Barcode functionality.
- Recipe calculation.
- Indian food expansion.
- Worldwide product expansion.
- User submissions.
- Admin moderation.
- Testing.

### Phase 3: Prototype

Build a small working prototype using:

- Worldwide packaged products.
- Indian ingredients.
- Indian household recipes.
- A few US products such as Kirkland products.
- A few European or Asian products.
- Barcode lookup.
- Search aliases.
- Recipe nutrition calculation.

### Phase 4: Testing

Test:

- Indian food searches.
- US branded-product searches.
- Kirkland products.
- Indian regional aliases.
- Barcode lookup.
- Raw versus cooked foods.
- Different serving units.
- Recipe variants.
- Duplicate products.
- Missing API results.
- Incorrect user-submitted data.
- API failures and fallback behavior.

## Important restrictions

- Do not delete existing working features.
- Do not replace the current database without explaining why.
- Do not hardcode thousands of fake food entries.
- Do not use AI-generated nutrition as verified data.
- Do not hide the source of nutritional information.
- Do not make major architectural changes before showing me the plan.
- Keep API keys and secrets in environment variables.
- Use caching and rate-limit protection for external APIs.
- Preserve the current design and user experience unless an improvement is necessary.

## Your first response

Do not write code yet.

First provide:

1. A summary of the existing nutrition architecture.
2. The main weaknesses you found.
3. The recommended worldwide food-data architecture.
4. The recommended Indian-food expansion strategy.
5. The database changes required.
6. The APIs or datasets worth evaluating.
7. A phased implementation plan.
8. Any questions or decisions you need from me.