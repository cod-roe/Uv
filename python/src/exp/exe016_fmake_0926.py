# %% [markdown]
## 特徴量作成！
# =================================================
# いろいろ作成

# %%
# ライブラリ読み込み
# =================================================
import datetime as dt

# import gc
# import json
import logging

# import re
import os
import sys
import pickle
from IPython.display import display
import warnings
# import zipfile

import numpy as np
import pandas as pd


# 可視化
import matplotlib.pyplot as plt
import seaborn as sns
import japanize_matplotlib


# lightGBM
import lightgbm as lgb

# sckit-learn
# from sklearn.preprocessing import StandardScaler, MinMaxScaler, LabelEncoder, OneHotEncoder

from sklearn.model_selection import StratifiedKFold  # ,train_test_split, KFold
from sklearn.metrics import roc_auc_score  # accuracy_score,confusion_matrix

import optuna

# %%
# Config
# =================================================

######################
# serial #
######################
serial_number = 19  # スプレッドシートAの番号

######################
# Data #
######################
comp_name = "Chronic_liver_disease"
# 評価：AUC（Area Under the Curve）

skip_run = False  # 飛ばす->True，飛ばさない->False

######################
# filename
######################
# vscode用
abs_path = os.path.abspath(__file__)  # /tmp/work/src/exp/_.py'
name = os.path.splitext(os.path.basename(abs_path))[0]
# Google Colab等用（取得できないためファイル名を入力）
# name = 'run001'

######################
# set dirs #
######################
DRIVE = os.path.dirname(os.getcwd())  # このファイルの親(scr)
INPUT_PATH = f"../input/{comp_name}/"  # 読み込みファイル場所
OUTPUT = os.path.join(DRIVE, "output")
OUTPUT_EXP = os.path.join(OUTPUT, name)  # 情報保存場所
EXP_MODEL = os.path.join(OUTPUT_EXP, "model")  # 学習済みモデル保存

######################
# Dataset #
######################
target_columns = "disease"
# sub_index = "index"

######################
# ハイパーパラメータの設定
######################
# lgbm初期値
# params = {
#     "boosting_type": "gbdt",
#     "objective": "binary",
#     "metric": "auc",
#     "learning_rate": 0.05,
#     "num_leaves": 32,
#     "n_estimators": 10000,
#     "random_state": 123,
#     "importance_type": "gain",
# }
params = {
    "num_leaves": 87,
    "min_child_samples": 20,
    "min_sum_hessian_in_leaf": 0.003370755864723668,
    "feature_fraction": 0.8690500471411575,
    "bagging_fraction": 0.8918658638247532,
    "lambda_l1": 0.017672334379224823,
    "lambda_l2": 0.03335121009317807,
    "boosting_type": "gbdt",
    "objective": "binary",
    "metric": "auc",
    "verbosity": -1,
    "learning_rate": 0.05,
    "n_estimators": 100000,
    "bagging_freq": 1,
    "random_state": 123,
}


# %%
# Utilities #
# =================================================


# 今の日時
def dt_now():
    dt_now = dt.datetime.now()
    return dt_now


# stdout と stderr をリダイレクトするクラス
class StreamToLogger:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.linebuf = ""

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass


# %%
# make dirs
# =================================================
def make_dirs():
    for d in [EXP_MODEL]:
        os.makedirs(d, exist_ok=True)
    print("フォルダ作成完了")


# %%
# ファイルの確認
# =================================================
def file_list(input_path):
    file_list = []
    for dirname, _, _filenames in os.walk(input_path):
        for i, _datafilename in enumerate(_filenames):
            print("=" * 20)
            print(i, _datafilename)
            file_list.append([_datafilename, os.path.join(dirname, _datafilename)])
    file_list = pd.DataFrame(file_list, columns=["ファイル名", "ファイルパス"])
    display(file_list)
    return file_list


# %%
# メモリ削減関数
# =================================================
def reduce_mem_usage(df):
    start_mem = df.memory_usage().sum() / 1024**2
    print(f"Memory usage of dataframe is {start_mem:.2f} MB")

    for col in df.columns:
        col_type = df[col].dtype

        if col_type != object:  # noqa: E721
            c_min = df[col].min()
            c_max = df[col].max()
            if str(col_type)[:3] == "int":
                if c_min > np.iinfo(np.int8).min and c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                elif c_min > np.iinfo(np.int16).min and c_max < np.iinfo(np.int16).max:
                    df[col] = df[col].astype(np.int16)
                elif c_min > np.iinfo(np.int32).min and c_max < np.iinfo(np.int32).max:
                    df[col] = df[col].astype(np.int32)
                elif c_min > np.iinfo(np.int64).min and c_max < np.iinfo(np.int64).max:
                    df[col] = df[col].astype(np.int64)
            else:
                if (
                    c_min > np.finfo(np.float16).min
                    and c_max < np.finfo(np.float16).max
                ):
                    df[col] = df[col].astype(np.float16)
                elif (
                    c_min > np.finfo(np.float32).min
                    and c_max < np.finfo(np.float32).max
                ):
                    df[col] = df[col].astype(np.float32)
                else:
                    df[col] = df[col].astypez(np.float64)
        else:
            pass

    end_mem = df.memory_usage().sum() / 1024**2
    print(f"Memory usage after optimization is: {end_mem:.2f} MB")
    print(f"Decreased by {100*((start_mem - end_mem) / start_mem):.2f}%")

    return df


# %%
# ファイルの読み込み
# =================================================
def load_data(file_index):
    # file_indexを引数に入力するとデータを読み込んでくれる
    if file_list["ファイル名"][file_index][-3:] == "csv":
        print(f"読み込んだファイル：{file_list['ファイル名'][file_index]}")
        df = reduce_mem_usage(pd.read_csv(file_list["ファイルパス"][file_index]))
        print(df.shape)
        display(df.head())

    elif file_list["ファイル名"][file_index][-3:] == "pkl" or "pickle":
        print(f"読み込んだファイル：{file_list['ファイル名'][file_index]}")
        df = reduce_mem_usage(pd.read_pickle(file_list["ファイルパス"][file_index]))
        print(df.shape)
        display(df.head())
    return df


# %%
# 前処理の定義 カテゴリ変数をcategory型に
# =================================================
def data_pre00(df):
    for col in df.columns:
        if df[col].dtype == "O":
            df[col] = df[col].astype("category")
    print("カテゴリ変数をcategory型に変換しました")
    df.info()
    return df


# %%
# 特徴量生成 exp002
# =================================================
def data_pre01(df):
    # Genderを数値化
    df["Gender"] = pd.get_dummies(df_train["Gender"], drop_first=True, dtype="uint8")
    # 特徴量1:直接ビリルビン/総ビリルビン比（D/T比） 3/2
    df["D_div_T_ex2"] = df["D_Bil"] / df["T_Bil"]

    # 特徴量2:AST/ALT比（De Ritis比 # 6/5
    df["AST_div_ALT_ex2"] = df["AST_GOT"] / df["ALT_GPT"]

    # 特徴量3:.フェリチン/AST比 フェリチンの代わりにタンパク質 7/6
    df["TP_div_AST_ex2"] = df["TP"] / df["AST_GOT"]

    # 特徴量4:.グロブリン  1/(8*9)
    df["Globulin_ex2"] = np.reciprocal(df["Alb"] / df["AG_ratio"])

    print("処理後:", df.shape)
    print("特徴量を生成しました(完了)")
    print("=" * 40)
    return df


# %%
# 特徴量作成 exp03
# =================================================
def data_pre02(df):
    # 特徴量1:ビリルビン/酵素比　総ビリルビン / ALT または 総ビリルビン / AST 2/5 2/6
    # df["TB_div_ALT_ex3"] = df["T_Bil"] / df["ALT_GPT"]
    # df["TB_div_AST_ex3"] = df["T_Bil"] / df["AST_GOT"]

    # 特徴量2: 総ビリルビン/ALP比  2/4
    df["TB_div_ALP_ex3"] = df["T_Bil"] / df["ALP"]

    # 特徴量3:アルブミン/ALT比 8/5
    df["Alb_div_ALT_ex3"] = df["Alb"] / df["ALT_GPT"]

    # 特徴量4:総タンパク/ALT比 7/5
    # df["TP_div_ALT_ex3"] = df["TP"] / df["ALT_GPT"]

    # 特徴量5:ALP/AST比またはALP/ALT比 4/6 4/5
    # df["ALP_div_AST_ex3"] = df["ALP"] / df["AST_GOT"]
    # df["ALP_div_ALT_ex3"] = df["ALP"] / df["ALT_GPT"]

    # 特徴量6:総ビリルビン / アルブミン 2/8
    # df["TB_div_Alb_ex3"] = df["T_Bil"] / df["Alb"]

    print("処理後:", df.shape)
    print("特徴量を生成しました(完了)")
    print("=" * 40)
    return df


# %%
# 学習関数の定義
# =================================================
def train_lgb(
    input_x,
    input_y,
    input_id,
    params,
    list_nfold=[0, 1, 2, 3, 4],
    n_splits=5,
):
    metrics = []
    imp = pd.DataFrame()
    train_oof = np.zeros(len(input_x))

    # cross-validation
    cv = list(
        StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=123).split(
            input_x, input_y
        )
    )

    # 1.学習データと検証データに分離
    for nfold in list_nfold:
        print("-" * 20, nfold, "-" * 20)
        print(dt_now().strftime("%Y年%m月%d日 %H:%M:%S"))

        idx_tr, idx_va = cv[nfold][0], cv[nfold][1]

        x_tr, y_tr = (
            input_x.loc[idx_tr, :],
            input_y[idx_tr],
        )
        x_va, y_va = (
            input_x.loc[idx_va, :],
            input_y[idx_va],
        )

        print(x_tr.shape, x_va.shape)

        # モデルの保存先名
        fname_lgb = os.path.join(EXP_MODEL, f"model_lgb_fold{nfold}.pickle")

        if not os.path.isfile(
            os.path.join(EXP_MODEL, f"model_lgb_fold{nfold}.pickle")
        ):  # if trained model, no training
            # train
            print("-------training start-------")
            model = lgb.LGBMClassifier(**params)
            model.fit(
                x_tr,
                y_tr,
                eval_set=[(x_tr, y_tr), (x_va, y_va)],
                callbacks=[
                    lgb.early_stopping(stopping_rounds=100, verbose=True),
                    lgb.log_evaluation(100),
                ],
            )

            # モデルの保存
            with open(fname_lgb, "wb") as f:
                pickle.dump(model, f, protocol=4)

        else:
            print("すでに学習済みのためモデルを読み込みます")
            with open(fname_lgb, "rb") as f:
                model = pickle.load(f)

        # evaluate
        y_tr_pred = model.predict_proba(x_tr)[:, 1]
        y_va_pred = model.predict_proba(x_va)[:, 1]
        metric_tr = roc_auc_score(y_tr, y_tr_pred)
        metric_va = roc_auc_score(y_va, y_va_pred)
        metrics.append([nfold, metric_tr, metric_va])
        print(f"[auc] tr:{metric_tr:.4f}, va:{metric_va:.4f}")

        # oof
        train_oof[idx_va] = y_va_pred

        # imp
        _imp = pd.DataFrame(
            {"col": input_x.columns, "imp": model.feature_importances_, "nfold": nfold}
        )
        imp = pd.concat([imp, _imp])

    print("-" * 20, "result", "-" * 20)

    # metric
    metrics = np.array(metrics)
    print(metrics)
    print(f"[cv] tr:{metrics[:,1].mean():.4f}+-{metrics[:,1].std():.4f}, \
        va:{metrics[:,2].mean():.4f}+-{metrics[:,1].std():.4f}")

    oof = f"[oof]{roc_auc_score(input_y, train_oof):.4f}"

    print(oof)

    # oof
    train_oof = pd.concat(
        [
            input_id,
            pd.DataFrame({"pred": train_oof}),
        ],
        axis=1,
    )

    # importance
    imp = imp.groupby("col")["imp"].agg(["mean", "std"]).reset_index(drop=False)
    imp.columns = ["col", "imp", "imp_std"]

    # stdout と stderr を一時的にリダイレクト
    stdout_logger = logging.getLogger("STDOUT")
    stderr_logger = logging.getLogger("STDERR")

    sys_stdout_backup = sys.stdout
    sys_stderr_backup = sys.stderr

    sys.stdout = StreamToLogger(stdout_logger, logging.INFO)
    sys.stderr = StreamToLogger(stderr_logger, logging.ERROR)
    print("-" * 20, "result", "-" * 20)
    print(dt_now().strftime("%Y年%m月%d日 %H:%M:%S"))
    print(name)
    print(input_x.shape)
    print(metrics)
    print(f"[cv] tr:{metrics[:,1].mean():.4f}+-{metrics[:,1].std():.4f}, \
        va:{metrics[:,2].mean():.4f}+-{metrics[:,1].std():.4f}")

    print(oof)

    print("-" * 20, "importance", "-" * 20)
    print(imp.sort_values("imp", ascending=False)[:10])

    # リダイレクトを解除
    sys.stdout = sys_stdout_backup
    sys.stderr = sys_stderr_backup

    return train_oof, imp, metrics


# %%
# 推論関数の定義 =================================================
def predict_lgb(
    input_x,
    input_id,
    list_nfold=[0, 1, 2, 3, 4],
):
    pred = np.zeros((len(input_x), len(list_nfold)))

    for nfold in list_nfold:
        print("-" * 20, nfold, "-" * 20)

        fname_lgb = os.path.join(EXP_MODEL, f"model_lgb_fold{nfold}.pickle")
        with open(fname_lgb, "rb") as f:
            model = pickle.load(f)

        # 推論
        pred[:, nfold] = model.predict_proba(input_x)[:, 1]

    # 平均値算出
    pred = pd.concat(
        [
            input_id,
            pd.DataFrame(pred.mean(axis=1)),
        ],
        axis=1,
    )
    print("Done.")

    return pred


# %% setup
# set up
# =================================================
# utils
warnings.filterwarnings("ignore")
sns.set(font="IPAexGothic")
###!%matplotlib inline
pd.options.display.float_format = "{:10.4f}".format  # 表示桁数の設定

# フォルダの作成
make_dirs()
# ファイルの確認
file_list = file_list(INPUT_PATH)

# utils
# ログファイルの設定
logging.basicConfig(
    filename=f"{OUTPUT_EXP}/log_{name}.txt", level=logging.INFO, format="%(message)s"
)
# ロガーの作成
logger = logging.getLogger()


# 出力表示数増やす
# pd.set_option('display.max_rows',None)
# pd.set_option('display.max_columns',None)


# %% ファイルの読み込み
# Load Data
# =================================================
# train
df_train = load_data(2)
# %%
# display(df_train.shape)
# df_train.info()


# %%
# df_train.describe().T
# %%
# df_train.describe(include="O").T

# %%
# これまでの処理
# ==========================================================
# df_train = data_pre01(df_train)
# df_train = data_pre02(df_train)

# %% [markdown]
## Main 分析start!
# =========================================================
# I_Bil(間接ビリルビン)
# df_train["I_Bil_ex16"] = df_train["T_Bil"] - df_train["D_Bil"]

# 特徴量2:AST/ALT比（De Ritis比 # 6/5
df_train["AST/ALT_ex2"] = df_train["AST_GOT"] / df_train["ALT_GPT"]

# 特徴量4:.グロブリン  1/(8*9) 式変更 TP-Alb
df_train["Glb_ex2"] = df_train["TP"] - df_train["Alb"]

# %%
# 特徴量1:直接ビリルビン/総ビリルビン比（D/T比） 3/2
df_train["DBil/TBil_ex2"] = df_train["D_Bil"] / df_train["T_Bil"]


# 特徴量3:.フェリチン/AST比 フェリチンの代わりにタンパク質 7/6
df_train["TP/AST_ex2"] = df_train["TP"] / df_train["AST_GOT"]
# %%
# 特徴量2: 総ビリルビン/ALP比  2/4
df_train["TB_div_ALP_ex3"] = df_train["T_Bil"] / df_train["ALP"]

# 特徴量3:アルブミン/ALT比 8/5
df_train["Alb_div_ALT_ex3"] = df_train["Alb"] / df_train["ALT_GPT"]


# %%
# sns.heatmap(
#     df_train[
#         [
#             "disease",
#             "Age",
#             "D_Bil",
#             "I_Bil_ex16",
#             "ALP",
#             "AST/ALT_ex2",
#             "AST_GOT",
#             "Glb_ex2",
#             "AG_ratio",
#         ]
#     ].corr(),
#     vmax=1,
#     vmin=-1,
#     annot=True,
# )

# %%
# sns.heatmap(
#     df_train[
#         [
#             "disease",
#             "Age",
#             "T_Bil",
#             "D_Bil",
#             "ALP",
#             "ALT_GPT",
#             "AST_GOT",
#             "TP",
#             "Alb",
#             "AG_ratio",
#         ]
#     ].corr(),
#     vmax=1,
#     vmin=-1,
#     annot=True,
# )

# %%
# 精度さがる
# df_train['AgeBand'] = pd.cut(df_train['Age'], [0,20,40,60,80,100],labels=False)
# df_train = pd.get_dummies(df_train, columns= ["AgeBand"])

# df_train['D_Bil'] = np.log10(df_train['D_Bil'] + 1)
# df_train['I_Bil_ex16'] = np.log10(df_train['I_Bil_ex16'] + 1)
# df_train['ALP'] = np.log10(df_train['ALP'] + 1)
# df_train['AST_GOT'] = np.log10(df_train['AST_GOT'] + 1)
# df_train['AST/ALT_ex2'] = np.log10(df_train['AST/ALT_ex2'] + 1)
# df_train['AG_ratio'] = np.log10(df_train['AG_ratio'] + 1)

# %%
# データセット作成
# =================================================
# drop_col = [target_columns, "T_Bil", "ALT_GPT", "TP", "Alb",]
# drop_col = ['disease','D_Bil','T_Bil','I_Bil_ex16','ALP','ALT_GPT','AST_GOT','TP','Alb','AG_ratio']


set_file = df_train
x_train = set_file.drop(
    [target_columns],
    axis=1,
)
y_train = set_file[target_columns]
id_train = pd.DataFrame(set_file.index)

print(x_train.shape, y_train.shape, id_train.shape)

# %%
x_train.head()
# %%
x_train = data_pre00(x_train)

# %%
# seed_values = [123,456,789]

# for i, seed_value in enumerate(seed_values):
#     print(f"Training model with seed {seed_value}")
#     params['random_state'] = seed_value  # シード値を変更
#     if not skip_run:
#         train_oof, imp, metrics = train_lgb(
#             x_train,
#             y_train,
#             id_train,
#             params,
#             list_nfold=[0, 1, 2, 3, 4],
#             n_splits=5,
#         )


# %%
params_base = {
    "boosting_type": "gbdt",
    "objective": "binary",
    "metric": "auc",
    "verbosity": -1,
    "learning_rate": 0.05,
    "n_estimators": 100000,
    "bagging_freq": 1,
    "random_state": 123,
}


# 目的関数の定義
def objective(trial):
    # 探索するハイパーパラメータ
    params_tuning = {
        "num_leaves": trial.suggest_int("num_leaves", 8, 256),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 200),
        "min_sum_hessian_in_leaf": trial.suggest_float(
            "min_sum_hessian_in_leaf", 1e-5, 1e-2, log=True
        ),
        "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
        "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
        "lambda_l1": trial.suggest_float("lambda_l1", 1e-2, 1e2, log=True),
        "lambda_l2": trial.suggest_float("lambda_l2", 1e-2, 1e2, log=True),
    }
    params_tuning.update(params_base)

    # モデル学習・評価
    list_metrics = []
    cv = list(
        StratifiedKFold(n_splits=5, shuffle=True, random_state=123).split(
            x_train, y_train
        )
    )

    list_fold = [0, 1, 2, 3, 4]  # 処理高速化のため1つ目のfoldのみとする
    for nfold in list_fold:
        idx_tr, idx_va = cv[nfold][0], cv[nfold][1]
        x_tr, y_tr = x_train.loc[idx_tr, :], y_train.loc[idx_tr]
        x_va, y_va = x_train.loc[idx_va, :], y_train.loc[idx_va]

        model = lgb.LGBMClassifier(**params_tuning)
        model.fit(
            x_tr,
            y_tr,
            eval_set=[(x_tr, y_tr), (x_va, y_va)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=100, verbose=True),
                lgb.log_evaluation(0),
            ],
        )

        y_va_pred = model.predict_proba(x_va)[:, 1]
        metric_va = roc_auc_score(y_va, y_va_pred)  # 評価指標をAUCにする
        list_metrics.append(metric_va)

    # 評価指標の算出
    metrics = np.mean(list_metrics)
    return metrics


# %%
# 7-50:最適化処理（探索の実行）
sampler = optuna.samplers.TPESampler(seed=123)
study = optuna.create_study(sampler=sampler, direction="maximize")
study.optimize(objective, n_trials=100, n_jobs=5)

# %%
trial = study.best_trial
print(f"auc(best)={trial.value:.4f}")
display(trial.params)
# %%
params_beat = trial.params
params_beat.update(params_base)
display(params_beat)


# %%
if not skip_run:
    train_oof, imp, metrics = train_lgb(
        x_train,
        y_train,
        id_train,
        params,
        list_nfold=[0, 1, 2, 3, 4],
        n_splits=5,
    )
# %%


# %%
# 説明変数の重要度の確認上位20
# =================================================
imp_sort = imp.sort_values("imp", ascending=False)
display(imp_sort[:20])
# imp_sort.to_csv(os.path.join(OUTPUT_EXP, f"imp_{name}.csv"), index=None)

# %%


# %%
# テストファイルの読み込み
# =================================================
df_test = load_data(1)

# %%
df_test = data_pre01(df_test)
df_test = data_pre02(df_test)


# %%
# 推論データのデータセット作成
set_file = df_test
x_test = set_file
id_test = pd.DataFrame(set_file.index)

print(x_test.shape, id_test.shape)
# %%
x_test.head()
# %%
# カテゴリ変数に変換
x_test = data_pre00(x_test)
# %%
# 推論処理
# =================================================
test_pred = predict_lgb(
    x_test,
    id_test,
    list_nfold=[0, 1, 2, 3, 4],
)
# %%
print(test_pred.shape)
test_pred.head()
# %%
# submitファイルの出力
# =================================================

# pred = (np.where(test_pred["pred"] >= 0.5, 1, 0)).astype(int)
# df_submit = pd.DataFrame(
#     {"PassengerId": id_test["PassengerId"], "Survived": pred}
# ).set_index("PassengerId")

# print(df_submit.shape)
# display(df_submit.head())

if not skip_run:
    test_pred.to_csv(
        os.path.join(OUTPUT_EXP, f"submission_{name}.csv"), index=False, header=False
    )


# %%
x_train.drop("Gender", axis=1).corr()
# %%