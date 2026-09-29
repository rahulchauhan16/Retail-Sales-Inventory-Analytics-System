"""Static reference data for the synthetic data generator.

Everything here is fictional: brand names, supplier names and people are invented.
Prices are GST-inclusive INR MRPs at the END of the data window.
"""

# --------------------------------------------------------------------------- categories
# types: (product type, min price, max price)
# markup: cost = price_ex_gst / (1 + markup)
# demand: relative popularity of the category's products
# trend:  yearly growth/decline of demand (used to create declining categories)
# ret:    baseline share of sold lines that get returned (generator assumption)
# qty:    mean units per order line
CATEGORIES = [
    dict(name="Mobiles & Accessories", code="MOB", gst=18, markup=(0.10, 0.25), demand=1.3, trend=0.08,
         ret=0.050, qty=1.05, parent="Electronics",
         types=[("Smartphone", 8999, 79999), ("Wireless Earbuds", 999, 6999), ("Power Bank", 799, 2999),
                ("Fast Charger", 499, 1999), ("Phone Case", 199, 999), ("Screen Guard", 149, 599),
                ("Smartwatch", 1999, 14999), ("USB Cable", 149, 699)],
         brands=["Zenix", "Orbito", "Kelvo", "Trion", "Lumo", "Vaayu"],
         variants=["Black", "Blue", "Silver", "Graphite", "Green", "White"]),
    dict(name="Laptops & Computers", code="LAP", gst=18, markup=(0.08, 0.20), demand=0.55, trend=0.02,
         ret=0.045, qty=1.05, parent="Electronics",
         types=[("Laptop", 32999, 129999), ("Wireless Mouse", 299, 1999), ("Keyboard", 499, 3999),
                ("Monitor", 6999, 24999), ("Printer", 3999, 15999), ("Pen Drive", 399, 1499),
                ("External SSD", 3499, 9999), ("Laptop Bag", 599, 2999)],
         brands=["Compex", "Datum", "Nuvo", "Pixelon", "Techra", "Ionix"],
         variants=["Standard", "Pro", "Lite", "Plus", "Black", "Grey"]),
    dict(name="Televisions & Audio", code="TVA", gst=18, markup=(0.10, 0.22), demand=0.5, trend=-0.22,
         ret=0.040, qty=1.0, parent="Electronics",
         types=[("LED TV", 10999, 89999), ("Soundbar", 2999, 24999), ("Bluetooth Speaker", 999, 7999),
                ("Headphones", 799, 9999), ("Home Theatre", 5999, 29999), ("Streaming Stick", 2499, 4999),
                ("TV Wall Mount", 399, 1499), ("Karaoke Mic", 999, 3499)],
         brands=["Vision", "Sonic", "Acoustix", "Bravia-X", "Clarion", "Mela"],
         variants=["32 inch", "43 inch", "50 inch", "Black", "Wireless", "Studio"]),
    dict(name="Home Appliances", code="HAP", gst=18, markup=(0.10, 0.22), demand=0.5, trend=0.05,
         ret=0.035, qty=1.02, parent="Appliances",
         types=[("Split AC", 29999, 59999), ("Refrigerator", 12999, 49999), ("Washing Machine", 11999, 39999),
                ("Ceiling Fan", 1799, 4999), ("Air Cooler", 5999, 14999), ("Water Heater", 3999, 11999),
                ("Vacuum Cleaner", 3999, 14999), ("Steam Iron", 799, 3499)],
         brands=["Frostline", "Aerocool", "Hydra", "Whirlon", "Homely", "Breeza"],
         variants=["1.5 Ton", "Inverter", "5 Star", "Compact", "Deluxe", "Silent"]),
    dict(name="Kitchen Appliances", code="KIT", gst=18, markup=(0.12, 0.28), demand=0.6, trend=0.06,
         ret=0.040, qty=1.2, parent="Appliances",
         types=[("Mixer Grinder", 1999, 5999), ("Microwave Oven", 5999, 17999), ("Induction Cooktop", 1499, 3999),
                ("Electric Kettle", 599, 1999), ("Air Fryer", 3499, 9999), ("Sandwich Toaster", 799, 2499),
                ("Water Purifier", 7999, 17999), ("Pressure Cooker", 899, 2999)],
         brands=["Rasoi", "Cookmate", "Flavo", "Spiceline", "Chefino", "Annapurna"],
         variants=["500W", "750W", "Steel", "Black", "Combo", "Large"]),
    dict(name="Men's Clothing", code="MEN", gst=12, markup=(0.45, 0.90), demand=1.2, trend=0.03,
         ret=0.110, qty=1.6, parent="Fashion",
         types=[("T-Shirt", 299, 1299), ("Formal Shirt", 699, 2499), ("Jeans", 899, 2999), ("Trousers", 799, 2499),
                ("Kurta", 599, 2499), ("Jacket", 1499, 5999), ("Track Pants", 499, 1499), ("Innerwear Pack", 299, 899)],
         brands=["UrbanEdge", "Kingsman-X", "Rugged", "Dapper", "Mensa", "Ravi & Sons"],
         variants=["M", "L", "XL", "Navy", "Grey", "Black"]),
    dict(name="Women's Clothing", code="WOM", gst=12, markup=(0.50, 1.00), demand=1.4, trend=0.07,
         ret=0.140, qty=1.6, parent="Fashion",
         types=[("Kurti", 399, 1899), ("Saree", 699, 7999), ("Leggings", 299, 999), ("Top", 349, 1499),
                ("Dress", 799, 3999), ("Palazzo", 399, 1499), ("Dupatta", 249, 1299), ("Jeans", 899, 2999)],
         brands=["Ananya", "Meher", "Vastra", "Ritika", "Nazaakat", "Sundari"],
         variants=["S", "M", "L", "Floral", "Solid", "Printed"]),
    dict(name="Kids' Wear", code="KID", gst=12, markup=(0.45, 0.85), demand=0.7, trend=-0.10,
         ret=0.090, qty=1.6, parent="Fashion",
         types=[("T-Shirt Set", 299, 999), ("Frock", 399, 1799), ("Shorts", 249, 799), ("Ethnic Set", 699, 2499),
                ("Sweatshirt", 499, 1499), ("School Uniform", 599, 1799), ("Pyjama Set", 349, 999), ("Rompers", 299, 899)],
         brands=["Chhotu", "Bubbly", "Tiny Steps", "Little Champ", "Gudda", "Munchkin"],
         variants=["2-3Y", "4-5Y", "6-7Y", "8-9Y", "Blue", "Pink"]),
    dict(name="Footwear", code="FTW", gst=12, markup=(0.40, 0.85), demand=1.0, trend=0.0,
         ret=0.120, qty=1.2, parent="Fashion",
         types=[("Running Shoes", 999, 5999), ("Casual Sneakers", 799, 3999), ("Formal Shoes", 1299, 4999),
                ("Sandals", 399, 1799), ("Flip Flops", 149, 699), ("Slippers", 199, 799), ("Ankle Boots", 1499, 5999),
                ("Kids School Shoes", 599, 1799)],
         brands=["Strider", "Pacer", "Walkwell", "Kolhapuri Co", "Bata-Lite", "Sole Mate"],
         variants=["UK 6", "UK 7", "UK 8", "UK 9", "Brown", "Black"]),
    dict(name="Grocery & Staples", code="GRO", gst=5, markup=(0.08, 0.18), demand=2.0, trend=0.12,
         ret=0.010, qty=2.8, parent="FMCG",
         types=[("Basmati Rice 5kg", 349, 899), ("Wheat Atta 10kg", 349, 649), ("Toor Dal 1kg", 129, 219),
                ("Sunflower Oil 1L", 119, 199), ("Sugar 1kg", 42, 60), ("Tea Leaves 500g", 199, 499),
                ("Pure Ghee 1L", 549, 899), ("Masala Combo", 49, 199), ("Biscuits Family Pack", 40, 150),
                ("Instant Noodles Pack", 60, 160)],
         brands=["Annadata", "Khet Fresh", "Golden Grain", "Desi Kitchen", "PureHarvest", "Mangal"],
         variants=["Pack of 1", "Pack of 2", "Economy Pack", "Value Pack"]),
    dict(name="Beverages", code="BEV", gst=12, markup=(0.10, 0.22), demand=1.3, trend=0.05,
         ret=0.010, qty=2.5, parent="FMCG",
         types=[("Cola 2L", 85, 110), ("Fruit Juice 1L", 90, 150), ("Packaged Water 12x1L", 120, 220),
                ("Energy Drink 4-Pack", 380, 520), ("Coffee Powder 200g", 249, 599), ("Green Tea 25 Bags", 149, 349),
                ("Soft Drink 6-Pack", 199, 329), ("Coconut Water 6-Pack", 249, 399)],
         brands=["FizzUp", "Tropica", "AquaPure", "Brewly", "Chai Ghar", "Coolo"],
         variants=["Regular", "Zero Sugar", "Family Size", "Mixed"]),
    dict(name="Personal Care", code="PER", gst=18, markup=(0.30, 0.65), demand=1.5, trend=0.09,
         ret=0.025, qty=1.8, parent="FMCG",
         types=[("Shampoo", 180, 650), ("Face Wash", 120, 450), ("Moisturiser", 199, 899), ("Toothpaste", 60, 220),
                ("Body Lotion", 199, 799), ("Deodorant", 149, 449), ("Sunscreen", 199, 799), ("Hair Oil", 90, 450),
                ("Beard Trimmer", 799, 2499), ("Soap Pack", 99, 349)],
         brands=["Glowvedic", "Nirmal", "Herbalife-X", "Kesar", "Tulsi Naturals", "Freshly"],
         variants=["100ml", "200ml", "Family Pack", "Sensitive", "Herbal"]),
    dict(name="Furniture & Decor", code="FUR", gst=18, markup=(0.25, 0.55), demand=0.4, trend=-0.12,
         ret=0.040, qty=1.05, parent="Home & Lifestyle",
         types=[("Office Chair", 3499, 14999), ("Study Table", 2999, 9999), ("Bookshelf", 2499, 8999),
                ("Sofa Set", 14999, 49999), ("Mattress", 5999, 24999), ("Wall Clock", 399, 1999),
                ("Table Lamp", 499, 1999), ("Curtain Pair", 599, 2499), ("Wall Art", 499, 2999)],
         brands=["Woodcraft", "Nilkamal-X", "Ghar Sajaa", "Homestead", "Teakwood Co", "Decora"],
         variants=["Walnut", "Oak", "Grey", "Beige", "Modern", "Classic"]),
    dict(name="Sports & Fitness", code="SPT", gst=12, markup=(0.30, 0.60), demand=0.7, trend=0.10,
         ret=0.050, qty=1.2, parent="Home & Lifestyle",
         types=[("Yoga Mat", 399, 1499), ("Dumbbell Set", 999, 4999), ("Cricket Bat", 799, 6999),
                ("Football", 399, 1499), ("Badminton Racquet", 499, 3499), ("Treadmill", 14999, 44999),
                ("Resistance Bands", 299, 999), ("Skipping Rope", 149, 499), ("Gym Bag", 599, 2499)],
         brands=["Fitora", "Champ", "Ace Sports", "Stamina", "Willow", "Kreeda"],
         variants=["Standard", "Pro", "Junior", "Blue", "Red", "Black"]),
    dict(name="Books & Stationery", code="BKS", gst=12, markup=(0.20, 0.40), demand=0.8, trend=-0.28,
         ret=0.020, qty=1.6, parent="Home & Lifestyle",
         types=[("Notebook Pack", 120, 450), ("Ball Pen Box", 100, 300), ("Fiction Paperback", 199, 499),
                ("Competitive Exam Guide", 349, 899), ("Engineering Textbook", 399, 1299), ("Geometry Box", 99, 349),
                ("Art Supplies Kit", 299, 1299), ("Desk Organiser", 199, 799), ("Planner Diary", 249, 699)],
         brands=["Pustak", "Classmate-X", "Vidya", "Lekhani", "Gyaan", "Sarthak"],
         variants=["Set of 3", "Pack of 6", "Premium", "A4", "A5", "Hardcover"]),
    dict(name="Toys & Games", code="TOY", gst=12, markup=(0.35, 0.70), demand=0.7, trend=-0.16,
         ret=0.050, qty=1.3, parent="Home & Lifestyle",
         types=[("Building Blocks", 299, 2499), ("Remote Control Car", 599, 2999), ("Board Game", 399, 1999),
                ("Soft Toy", 249, 1299), ("Jigsaw Puzzle", 199, 899), ("Doll House", 799, 2999),
                ("Art & Craft Set", 249, 999), ("Science Kit", 499, 1999)],
         brands=["Playzee", "Khilona", "Brainy", "Funtoo", "Tinkerz", "Rangeela"],
         variants=["Ages 3+", "Ages 6+", "Deluxe", "Mini", "Family", "Classic"]),
]

# Categories where seasonality boosts demand: {category name: {month number: multiplier}}
CATEGORY_SEASONALITY = {
    "Home Appliances": {3: 1.4, 4: 1.7, 5: 1.7, 6: 1.4},
    "Kitchen Appliances": {10: 1.3, 11: 1.3},
    "Men's Clothing": {10: 1.4, 11: 1.4, 12: 1.2},
    "Women's Clothing": {10: 1.5, 11: 1.4, 12: 1.2},
    "Kids' Wear": {6: 1.5, 10: 1.3},
    "Books & Stationery": {6: 1.8, 7: 1.8},
    "Beverages": {4: 1.4, 5: 1.5, 6: 1.3},
    "Sports & Fitness": {1: 1.3, 2: 1.2},
    "Toys & Games": {10: 1.3, 11: 1.4, 12: 1.4},
}

# Case-variant category rows planted on purpose (data-quality scenario)
CATEGORY_VARIANTS = [("home appliances", "Home Appliances"), ("FOOTWEAR", "Footwear")]

# --------------------------------------------------------------------------- stores
# code, name, city, state, region, opened, size weight, store_type
STORES = [
    ("MUM01", "Mumbai Andheri", "Mumbai", "Maharashtra", "West", "2018-04-10", 1.50, "STORE"),
    ("DEL01", "Delhi Connaught Place", "Delhi", "Delhi", "North", "2017-09-01", 1.40, "STORE"),
    ("BLR01", "Bengaluru Indiranagar", "Bengaluru", "Karnataka", "South", "2019-02-15", 1.40, "STORE"),
    ("HYD01", "Hyderabad Banjara Hills", "Hyderabad", "Telangana", "South", "2019-11-20", 1.10, "STORE"),
    ("CHE01", "Chennai T Nagar", "Chennai", "Tamil Nadu", "South", "2020-03-05", 1.00, "STORE"),
    ("KOL01", "Kolkata Salt Lake", "Kolkata", "West Bengal", "East", "2020-10-12", 0.90, "STORE"),
    ("PUN01", "Pune Koregaon Park", "Pune", "Maharashtra", "West", "2021-06-18", 1.00, "STORE"),
    ("AMD01", "Ahmedabad SG Highway", "Ahmedabad", "Gujarat", "West", "2021-12-01", 0.80, "STORE"),
    ("JAI01", "Jaipur Malviya Nagar", "Jaipur", "Rajasthan", "North", "2022-08-25", 0.55, "STORE"),
    ("CHD01", "Chandigarh Sector 17", "Chandigarh", "Chandigarh", "North", "2023-06-01", 0.50, "STORE"),
    ("LKO01", "Lucknow Gomti Nagar", "Lucknow", "Uttar Pradesh", "North", "2024-03-15", 0.45, "STORE"),
    ("ONL01", "Online Fulfilment Hub", "Mumbai", "Maharashtra", "West", "2022-01-10", 0.0, "ONLINE_WAREHOUSE"),
]

# Customers outside store cities: city -> (state, index of the nearest physical store)
OTHER_CITIES = {
    "Surat": ("Gujarat", 7), "Vadodara": ("Gujarat", 7), "Nagpur": ("Maharashtra", 0), "Nashik": ("Maharashtra", 6),
    "Indore": ("Madhya Pradesh", 0), "Bhopal": ("Madhya Pradesh", 1), "Kochi": ("Kerala", 4),
    "Coimbatore": ("Tamil Nadu", 4), "Visakhapatnam": ("Andhra Pradesh", 3), "Mysuru": ("Karnataka", 2),
    "Patna": ("Bihar", 5), "Bhubaneswar": ("Odisha", 5), "Kanpur": ("Uttar Pradesh", 10), "Noida": ("Uttar Pradesh", 1),
    "Gurugram": ("Haryana", 1), "Udaipur": ("Rajasthan", 8), "Ludhiana": ("Punjab", 9), "Dehradun": ("Uttarakhand", 1),
}

# --------------------------------------------------------------------------- people (fictional combinations)
FIRST_M = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Rahul", "Amit", "Vikram", "Sanjay", "Manish",
           "Nikhil", "Pranav", "Siddharth", "Harsh", "Yash", "Deepak", "Suresh", "Rajesh", "Anil", "Kunal", "Varun",
           "Gaurav", "Mohit", "Ashish", "Tarun", "Naveen", "Ramesh", "Vijay", "Abhishek"]
FIRST_F = ["Ananya", "Diya", "Isha", "Kavya", "Meera", "Neha", "Pooja", "Priya", "Riya", "Sneha", "Shreya", "Tanvi",
           "Aishwarya", "Divya", "Nisha", "Swati", "Anjali", "Kritika", "Lakshmi", "Radha", "Sunita", "Rekha", "Jyoti",
           "Pallavi", "Sakshi", "Bhavna", "Mansi", "Ritu", "Komal", "Nandini"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Shah", "Mehta", "Joshi", "Iyer", "Nair", "Reddy",
        "Rao", "Menon", "Pillai", "Das", "Banerjee", "Chatterjee", "Mukherjee", "Ghosh", "Kulkarni", "Deshmukh",
        "Patil", "Jain", "Agarwal", "Bansal", "Malhotra", "Kapoor", "Chopra", "Khanna", "Bhatt", "Trivedi", "Yadav",
        "Mishra", "Pandey", "Tiwari", "Saxena", "Chauhan", "Thakur", "Naidu"]
EMAIL_DOMAINS = ["example.com", "example.org", "example.net"]   # reserved, non-routable domains

SEGMENTS = [
    # name, description, share of customers, order-frequency multiplier, extra items per order (Poisson mean)
    ("Regular", "Standard retail shoppers", 0.62, 1.0, 1.0),
    ("Premium", "Loyalty members with higher spend", 0.14, 1.8, 1.4),
    ("Corporate", "Business / bulk buyers", 0.06, 1.3, 1.7),
    ("Student", "Students with lower basket values", 0.18, 0.8, 0.7),
]

JOB_TITLES_STORE = ["Sales Associate", "Cashier", "Inventory Executive", "Sales Associate", "Customer Service Executive"]
JOB_TITLES_HUB = ["Fulfilment Executive", "Fulfilment Executive", "Online Order Coordinator", "Inventory Executive"]

SUPPLIER_PREFIX = ["Bharat", "Shree", "Sai", "Aditya", "Krishna", "Om", "Rajdhani", "Jai", "Navjeevan", "Tirupati",
                   "Sunrise", "Apex", "Prime", "Metro", "Global", "Kaveri", "Ganga", "Himalaya", "Deccan", "Konkan",
                   "Malabar", "Vindhya", "Aravali", "Nilgiri", "Sahyadri"]
SUPPLIER_SUFFIX = ["Pvt Ltd", "Traders", "Enterprises", "Industries", "& Co", "Distributors", "LLP"]
SUPPLIER_DOMAIN = {  # by first category code of the supplier
    "MOB": "Mobile Distributors", "LAP": "Computer Hub", "TVA": "Audio Video", "HAP": "Appliances",
    "KIT": "Kitchenware", "MEN": "Garments", "WOM": "Textiles", "KID": "Kidswear", "FTW": "Footwear",
    "GRO": "Foods", "BEV": "Beverages", "PER": "FMCG", "FUR": "Furnishings", "SPT": "Sports Goods",
    "BKS": "Stationers", "TOY": "Toys",
}
GSTIN_STATE_CODES = ["27", "07", "29", "36", "33", "19", "24", "08", "09", "03"]
