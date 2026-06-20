#%% Import libraries
import pandas as pd 
import numpy as np

#%% Load data
df = pd.read_csv("data/france_ml_data.csv")

#%% Display data
df.head()

#%% Data info
df.info()

#%% Check duplicates
dupes_all = df[df.duplicated(keep=False)]
dupes_all.sort_values(by=df.columns.tolist())

#%% Check for missing values
df.isnull().sum()

#%% Check datetime columns
df[["date", "datetime_utc", "datetime_local"]]

#%% Cleaning function
def clean_data(df):
    df = df.drop_duplicates()
    df = df.drop(columns=["locality"])
    df.loc[df["observed_count"] == 1, "std"] = 0
    # since missing values in the std feature happens only when observed_count = 1, 
    # we can set std to 0 for every row where observed_count = 1
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    df["datetime_local"] = pd.to_datetime(df["datetime_local"], utc=True)
    df["date"] = pd.to_datetime(df["date"])
    return df

df_clean = clean_data(df)
df_clean.head()

#%% Saved clean data
df_clean.to_csv("data/france_ml_data_clean.csv", index=False)