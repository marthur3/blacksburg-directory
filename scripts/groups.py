"""Maps Overture category text to directory groups. First match wins.

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
                          "pediatric*", "physical"]),
    ("Lodging", ["hotel*", "motel*", "lodging", "accommodation*", "inn", "hostel*",
                 "campground*", "resort*", "bed"]),
    ("Food & Drink", ["restaurant*", "cafe*", "coffee", "bakery", "bakeries", "bar", "bars",
                      "pub", "pubs", "brewer*", "pizza", "food", "dessert*", "ice", "winer*",
                      "eat", "sandwich*", "deli", "tea", "diner*", "burger*", "taco*",
                      "bagel*", "donut*", "catering", "caterer*", "juice", "barbecue",
                      "steakhouse*", "sushi", "distiller*", "cidery"]),
    ("Auto", ["auto", "automotive", "car", "cars", "gas", "tire*", "towing", "mechanic*",
              "dealership*", "motorcycle*", "oil", "collision", "truck*", "fuel"]),
    ("Fitness & Recreation", ["gym*", "fitness", "yoga", "pilates", "park", "parks", "sport*",
                              "recreation*", "golf", "trail*", "martial", "climbing", "pool",
                              "playground*", "stadium*", "dance", "crossfit"]),
    ("Home & Trades", ["contractor*", "plumb*", "electrician*", "hvac", "roof*", "landscap*",
                       "cleaning", "pest", "construction", "painter*", "moving", "mover*",
                       "handyman", "flooring", "remodel*", "carpent*", "locksmith*",
                       "storage", "heating", "builder*", "paving", "fencing", "lawn"]),
    ("Professional Services", ["lawyer*", "attorney*", "legal", "account*", "insurance",
                               "financial", "bank", "banks", "credit", "real", "realtor*",
                               "consult*", "marketing", "tax", "notary", "engineer*",
                               "architect*", "software", "advertising", "printing",
                               "mortgage", "investment*", "property", "staffing", "design"]),
    ("Education", ["school*", "college*", "university", "education*", "tutor*", "preschool*",
                   "daycare", "child", "library", "libraries", "academy"]),
    ("Arts & Entertainment", ["theater*", "theatre*", "cinema*", "museum*", "gallery",
                              "galleries", "music", "entertainment", "art", "arts", "event",
                              "events", "venue*", "bowling", "arcade*", "nightlife",
                              "attraction*", "performing"]),
    ("Community & Civic", ["church*", "religious", "government", "nonprofit*", "community",
                           "post", "police", "fire", "civic", "charit*", "mosque*",
                           "synagogue*", "temple*", "organization*", "public", "social"]),
    ("Shopping", ["store*", "shop", "shops", "shopping", "retail*", "boutique*", "grocer*",
                  "supermarket*", "market", "florist*", "jewel*", "clothing", "furniture",
                  "hardware", "bookstore*", "gift", "thrift", "pawn", "liquor", "convenience",
                  "department", "electronics", "antique*", "nursery", "outlet*"]),
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
