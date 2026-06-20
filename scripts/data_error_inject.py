# %% Import libraries
import numpy as np
import pandas as pd
import os
np.random.seed(36)
prob = 0.2

# %% Required error types
def completeness(df):
    df = df.copy()
    cols = ["location_id", "value_avg", "min", "max", "q25", "median", "q75", "std"]
    
    for i in cols:
        mask = np.random.rand(len(df)) < prob
        df.loc[mask, i] = np.nan
        
    return df

def validity(df):
    df = df.copy()
    mask = np.random.rand(len(df)) < prob
    df.loc[mask, "latitude"] = np.random.choice([999, -999, 727, -727], size=mask.sum())

    mask = np.random.rand(len(df)) < prob
    df.loc[mask, "longitude"] = np.random.choice([999, -999, 727, -727], size=mask.sum())
    
    return df

def consistency(df):
    df = df.copy()
    wrong_units = ["cm", "kg", "unknown"]
    mask = np.random.rand(len(df)) < prob
    df.loc[mask, "units"] = np.random.choice(wrong_units, size=mask.sum())

    return df

def schema(df):
    df = df.copy()
    if np.random.rand() < prob:
        df.drop(columns=["parameter"], inplace=True)

    return df

def type_data(df):
    df = df.copy()
    cols = ["expected_count", "observed_count"]
    ones = ["one", "un", "uno", "mot"]

    for col in cols:
        mask = np.random.rand(len(df)) < prob
        df[col] = df[col].astype(object)
        df.loc[mask, col] = np.random.choice(ones, size=mask.sum())

    return df

# %% Additional error types
def duplicates(df):
    df = df.copy()
    mask = np.random.rand(len(df)) < prob
    dup_rows = df[mask]
    df = pd.concat([df, dup_rows], ignore_index=True)

    return df

def outliers(df):
    df = df.copy()
    cols = ["value_avg", "min", "max", "q25", "median", "q75"]
    
    for i in cols:
        mask = np.random.rand(len(df)) < prob
        factor = np.random.choice([0.001, 1000], size=mask.sum())
        df.loc[mask, i] *= factor
        
    return df

#%% Main
input_fol = "data/raw_data"
output_fol = "data/errored_data"
os.makedirs(output_fol, exist_ok=True)

def inject_errors(input):
    files = os.listdir(input_fol)
    for f in files:
        path = os.path.join(input_fol, f)
        df = pd.read_csv(path)
        df = completeness(df)
        df = validity(df)
        df = consistency(df)
        df = schema(df)
        df = type_data(df)
        df = duplicates(df)
        df = outliers(df)
        name, ext = os.path.splitext(f)
        new_filename = f"{name}_errored{ext}"
        save_path = os.path.join(output_fol, new_filename)
        df.to_csv(save_path, index=False)

    print("Done")

inject_errors(input_fol)