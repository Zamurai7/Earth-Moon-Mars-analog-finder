import pandas as pd

# Load
df = pd.read_csv("analog_sites_enriched_v3.csv")

print("Before cleaning:")
print(f"  Rows: {len(df)}")
print(f"  Missing values:\n{df.isnull().sum()}")
print(f"  Duplicates: {df.duplicated().sum()}")

# Remove duplicates
df = df.drop_duplicates()

# Remove rows with any missing value
df = df.dropna()

print("\nAfter cleaning:")
print(f"  Rows: {len(df)}")

# Export
df.to_csv("Earths_Locations_clean.csv", index=False)
print("\nDone. Saved as cleaned_data.csv")