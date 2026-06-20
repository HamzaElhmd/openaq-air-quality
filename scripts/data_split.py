#%% Import libraries
import pandas as pd
import numpy as np
import os
df = pd.read_csv("data/france_ml_data_clean.csv")

# %% Split data into 1000 files
chunks = np.array_split(df.values, 1000)

# %% Export split data
output_folder = "data/raw_data"
os.makedirs(output_folder, exist_ok=True)
for i, chunk in enumerate(chunks):
    chunk_df = pd.DataFrame(chunk, columns=df.columns)
    chunk_df.to_csv(os.path.join(output_folder, f"france_ml_data_clean_{i+1}.csv"),index=False)