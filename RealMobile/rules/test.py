import pandas as pd

# 读取human_eval.csv
df_human = pd.read_csv('rules/human_eval.csv')
print("列名:", df_human.columns.tolist())
print("\n前几行:")
print(df_human.head())
print("\nsid和query的对应关系:")
print(df_human[['sid', 'query']].head(10))