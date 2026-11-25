"""Maps Overture places to directory groups.

Order of trust: KIND_GROUP (exact category), keyword rules on the category, keyword rules on
the taxonomy text, then the listing name. Names come last because they mislead: "Bed Bath &
Beyond" is not lodging.

A keyword ending in * matches any token with that prefix; others match a whole token.
"""
import re

RULES = [
    ("Pets", ["pet", "pets", "veterinar*", "kennel*", "animal*", "groomer*", "dog"]),
    ("Beauty & Personal Care", ["salon*", "barber*", "spa", "spas", "beauty", "nail", "nails",
                                "tattoo*", "massage", "hair", "cosmetic*", "tanning"]),
    ("Health & Medical", ["doctor*", "dentist*", "dental", "medical", "health", "clinic*",
                          "hospital*", "pharmac*", "chiropract*", "optomet*", "physician*",
                          "counsel*", "therap*", "psycholog*", "urgent", "orthodont*",
                          "pediatric*", "physical", "wellness", "acupuncture"]),
    ("Lodging", ["hotel*", "motel*", "lodging", "accommodation*", "inn", "hostel*",
                 "campground*", "resort*", "bed"]),
    ("Food & Drink", ["restaurant*", "cafe*", "coffee", "bakery", "bakeries", "bar", "bars",
                      "pub", "pubs", "brewer*", "pizza", "food", "dessert*", "ice", "winer*",
                      "eat", "sandwich*", "deli", "tea", "diner*", "burger*", "taco*",
                      "bagel*", "donut*", "catering", "caterer*", "juice", "barbecue",
                      "steakhouse*", "sushi", "distiller*", "cidery"]),
    ("Auto", ["auto", "automotive", "car", "cars", "gas", "tire*", "towing", "mechanic*",
              "dealership*", "motorcycle*", "oil", "collision", "truck*", "fuel",
              "charging", "fueling", "vehicle"]),
    ("Fitness & Recreation", ["gym*", "fitness", "yoga", "pilates", "park", "parks", "sport*",
                              "recreation*", "golf", "trail*", "martial", "climbing", "pool",
                              "playground*", "stadium*", "dance", "crossfit"]),
    ("Home & Trades", ["contractor*", "plumb*", "electrician*", "hvac", "roof*", "landscap*",
                       "cleaning", "pest", "construction", "painter*", "moving", "mover*",
                       "handyman", "flooring", "remodel*", "carpent*", "locksmith*",
                       "storage", "heating", "builder*", "paving", "fencing", "lawn",
                       "laundry", "manufacturer", "driveway"]),
    ("Professional Services", ["lawyer*", "attorney*", "legal", "account*", "insurance",
                               "financial", "bank", "banks", "credit", "real", "realtor*",
                               "consult*", "marketing", "tax", "notary", "engineer*",
                               "architect*", "software", "advertising", "printing",
                               "mortgage", "investment*", "property", "staffing", "design",
                               "corporate", "professional", "logistics", "shipping",
                               "telecom", "telecommunications", "security"]),
    ("Education", ["school*", "college*", "university", "education*", "tutor*", "preschool*",
                   "daycare", "child", "library", "libraries", "academy"]),
    ("Arts & Entertainment", ["theater*", "theatre*", "cinema*", "museum*", "gallery",
                              "galleries", "music", "entertainment", "art", "arts", "event",
                              "events", "venue*", "bowling", "arcade*", "nightlife",
                              "attraction*", "performing", "historic", "monument",
                              "cultural", "radio"]),
    ("Community & Civic", ["church*", "religious", "government", "nonprofit*", "community",
                           "post", "police", "fire", "civic", "charit*", "mosque*",
                           "synagogue*", "temple*", "organization*", "public", "social",
                           "worship", "cemetery", "funeral", "jewish", "muslim", "hindu",
                           "buddhist"]),
    ("Shopping", ["store*", "shop", "shops", "shopping", "retail*", "boutique*", "grocer*",
                  "supermarket*", "market", "florist*", "jewel*", "clothing", "furniture",
                  "hardware", "bookstore*", "gift", "thrift", "pawn", "liquor", "convenience",
                  "department", "electronics", "antique*", "nursery", "outlet*",
                  "wholesaler", "supplier", "distributor"]),
]

GROUPS = [g for g, _ in RULES] + ["Other"]


def assign_group(text: str) -> str:
    tokens = re.findall(r"[a-z]+", (text or "").lower())
    if not tokens:
        return "Other"
    for group, words in RULES:
        for w in words:
            if w.endswith("*"):
                if any(t.startswith(w[:-1]) for t in tokens):
                    return group
            elif w in tokens:
                return group
    return "Other"


# Exact categories the keyword rules get wrong or cannot place.
KIND_GROUP = {
    "home service": "Home & Trades",
    "campus building": "Education",
    "research institute": "Education",
    "place of learning": "Education",
    "casual eatery": "Food & Drink",
    "non alcoholic beverage venue": "Food & Drink",
    "diagnostics imaging or lab service": "Health & Medical",
    "complementary and alternative medicine": "Health & Medical",
    "surgery": "Health & Medical",
    "reproductive perinatal and womens care": "Health & Medical",
    "senior living facility": "Health & Medical",
    "outpatient care facility": "Health & Medical",
    "emergency department": "Health & Medical",
    "wellness service": "Beauty & Personal Care",
    "technical service": "Professional Services",
    "media service": "Professional Services",
    "b2b service": "Professional Services",
    "b2b science and technology service": "Professional Services",
    "environmental or ecological service": "Professional Services",
    "travel service": "Professional Services",
    "apartment": "Professional Services",
    "condominium": "Professional Services",
    "family service": "Community & Civic",
    "food bank": "Community & Civic",
    "courthouse": "Community & Civic",
    "military site": "Community & Civic",
    "jail or prison": "Community & Civic",
    "electric utility provider": "Community & Civic",
    "water utility provider": "Community & Civic",
    "garden": "Fitness & Recreation",
    "nature reserve": "Fitness & Recreation",
    "rv park": "Lodging",
    "books music and video store": "Shopping",
    "arts crafts and hobby store": "Shopping",
    "sporting goods store": "Shopping",
}


def group_for(category: str, taxonomy_text: str = "", name: str = "") -> str:
    kind = (category or "").replace("_", " ").strip().lower()
    if kind in KIND_GROUP:
        return KIND_GROUP[kind]
    for text in (kind, taxonomy_text, name):
        group = assign_group(text)
        if group != "Other":
            return group
    return "Other"


def name_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def is_excluded(cfg: dict, rec: dict) -> bool:
    """True if config exclude_ids / exclude_names match this listing."""
    if (rec.get("id") or "") in set(cfg.get("exclude_ids") or []):
        return True
    key = name_key(rec.get("name") or "")
    names = {name_key(n) for n in (cfg.get("exclude_names") or [])}
    return bool(key) and key in names
