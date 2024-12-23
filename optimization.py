"""
Module to train, optimize and evulate ML model 

Author: Son Gyo Jung
Email: sgj13@cam.ac.uk
"""  
import os   
import numpy as np                                                                                                                                                                               
import pandas as pd
import joblib
import matplotlib.pyplot as plt

from sklearn.preprocessing import label_binarize, MinMaxScaler
from sklearn.metrics import RocCurveDisplay, PrecisionRecallDisplay
from sklearn.metrics import multilabel_confusion_matrix, roc_curve, roc_auc_score, max_error, \
                            auc, f1_score, classification_report, recall_score, precision_recall_curve, \
                            balanced_accuracy_score, confusion_matrix, accuracy_score, average_precision_score, \
                            hamming_loss, matthews_corrcoef, mean_squared_error, mean_absolute_error, r2_score, \
                            confusion_matrix, ConfusionMatrixDisplay, explained_variance_score


from lightgbm.sklearn import LGBMClassifier, LGBMRegressor
from xgboost import XGBClassifier, XGBRegressor

from skopt import forest_minimize, gbrt_minimize, gp_minimize, dummy_minimize
from sklearn.model_selection import cross_val_score
from skopt.utils import use_named_args
from skopt.space import Real, Integer
from skopt import dump, load
from skopt.plots import plot_convergence, plot_objective, plot_evaluations
from skopt import dump, load

import statsmodels.api as sm
import statsmodels.formula.api as smf

from itertools import cycle


class optimization():
    """
    Optimize and evulate ML model 

    args: 
    (1) path_to_train_data (type:str); location of the training data 
    (2) path_to_test_data (type:str); location of the test data 
    (3) path_to_save (type:str); location to save new data files
    (4) target (type:str) - name of target variable
    (5) features (list) - list of exploratory features (e.g. those with multicollinearity reduced)
    (6) scaled (bool) - whether the features are scaled in the training dataset
    (7) problem (type:str) - whether it is a 'classification' or 'regression' problem
    
    return: performance evaluation of ML model
    """
    def __init__(self, path_to_train_data, path_to_test_data, path_to_save, target, features, scaled, problem, *args, **kwargs):
        self.path_to_save = path_to_save
        self.sample_train = joblib.load(path_to_train_data)  
        self.sample_test = joblib.load(path_to_test_data)

        # Define input and target variables
        if isinstance(features, list):
            self.RFE_features = features
        else:
            self.RFE_features = joblib.load(features) 

        self.target = target

        print('Name of target column: ', self.target)
        print('No. of exploratory features: ', len(self.RFE_features))

        self.problem = problem
        self.estimator = kwargs.get('estimator')

        if scaled is False:
            # Scale the features
            scaling = MinMaxScaler(feature_range=(0, 1))

            self.sample_train[self.RFE_features] = pd.DataFrame(
                                                scaling.fit_transform(self.sample_train[self.RFE_features].values),
                                                columns=self.sample_train[self.RFE_features].columns,
                                                index=self.sample_train[self.RFE_features].index
                                            )
                                            

            self.sample_test[self.RFE_features] = pd.DataFrame(
                                                scaling.transform(self.sample_test[self.RFE_features].values),
                                                columns=self.sample_test[self.RFE_features].columns,
                                                index=self.sample_test[self.RFE_features].index
                                            )
            

    def base_model(self, boosting_method, *args, **kwargs):
        """
        Choose baseline model

        args: 
            (1) boosting_method - 'lightGBM', 'XGBoost'
            (2) objective (type:str) - 'binary', 'multiclass', 'multi:softprob'

        return: baseline model
        """
        self.boosting_method = boosting_method
        objective = kwargs.get('objective')

        if self.problem == 'classification':
            if self.boosting_method == 'lightGBM':
                self.estimator = LGBMClassifier(
                                                boosting_type='gbdt',
                                                objective=objective,
                                                random_state=42,
                                                importance_type='gain',
                                                max_depth=-1,
                                                verbose=-1
                                                )


            elif self.boosting_method == 'XGBoost':
                    self.estimator = XGBClassifier(
                                                    objective=objective,
                                                    booster='gbtree',
                                                    random_state=42,
                                                    importance_type='total_gain'
                                                    )

        elif self.problem == 'regression':
            if self.boosting_method == 'lightGBM':
                self.estimator = LGBMRegressor(
                                                boosting_type ='gbdt',
                                                random_state=42,
                                                importance_type='gain',
                                                max_depth=-1,
                                                verbose=-1
                                                )


            elif self.boosting_method == 'XGBoost':
                self.estimator = XGBClassifier(
                                                objective='reg:squarederror',
                                                booster='gbtree',
                                                random_state=42,
                                                importance_type='total_gain'
                                                )

        return self.estimator


    def set_hyperparameters(self):
        """
        Define the hyperparameter space where optimization will be conducted

        args: None
        return: hyperparameter space 
        """
        self.space = [
                    Real(0.0001, 1.0, name='learning_rate', prior='log-uniform'),
                    Integer(100, 3000, name='n_estimators'),
                    Integer(10, 400, name='num_leaves')

                    # Other parameters can be added e.g.
                    # Integer(10, 100, name='max_depth'),
                    # Real(1, 10, name='min_child_weight', prior='uniform'), 
                    ]

        self.hyperparameters = [
                                'learning_rate',
                                'n_estimators',
                                'num_leaves'
                                ]

        return self.hyperparameters, self.space


    def run(self, optimization_method, n_calls=100, x0=None):
        """
        Execute optimization using one of the methods

        args: optimization_method (type:str); choose one of the following :- dummy_minimize, gp_minimize, gbrt_minimize, forest_minimize
        return: value of the hyperparameters 
        """
        @use_named_args(self.space)
        def objective(**params):
            """
            Define the objective function
            """
            # Performance metric to consider
            if self.problem == 'classification':
                # scoring = 'f1_weighted'
                scoring = 'roc_auc'
                
            elif self.problem == 'regression':
                scoring = 'neg_root_mean_squared_error'

            self.estimator.set_params(**params)
            
            print('\n', params, '\n')
            
            score = -np.mean(cross_val_score(
                                            self.estimator, 
                                            self.sample_train[self.RFE_features], 
                                            self.sample_train[self.target], 
                                            cv = 5, 
                                            n_jobs = -1, 
                                            scoring = scoring
                                            )
                            )
            
            print('Score: ', score, '\n')
            return score


        self.optimization_method = optimization_method

        if self.optimization_method == 'random_search':
            opt_method = dummy_minimize

        elif self.optimization_method == 'bayesian':
            opt_method = gp_minimize

        elif self.optimization_method == 'gradient_bossted_trees':
            opt_method = gbrt_minimize

        elif self.optimization_method == 'decision_trees':
            opt_method = forest_minimize

        self.opt = opt_method(
                            func = objective, 
                            dimensions = self.space, 
                            n_calls = n_calls, 
                            verbose = 1,
                            x0 = x0 
                            ) 

        self.values = list()

        print('\n', '*** Optimal hyperparameters *** ')

        for i in range(0, len(self.opt.x)): 
            print('{}: {}'.format(self.hyperparameters[i], self.opt.x[i]))
            self.values.append(self.opt.x[i])

        dump(opt_method, os.path.join(self.path_to_save, r'optimization_data_' + self.target + '.pkl'))

        print('Saved:', 'optimization_data_' + self.target + '.pkl')



    def convergence_plot(self):
        """
        plot convergence plot of the optimization

        args: None
        return: convergence plot
        """
        # Setting up the figure
        fig, ax = plt.subplots(figsize = (8,8))

        fontsize = 25

        plot = plot_convergence((str(self.optimization_method), self.opt))

        plot.legend(loc="best", prop={'size': fontsize}, numpoints=1)
        ax.grid(False)
        ax.set_title(' ', fontsize = 25)
        ax.set_xlabel('Number of iterations', fontsize = fontsize)
        ax.set_ylabel('Objective minimum', fontsize = fontsize) 
        ax.tick_params(axis='both', which='major', labelsize=fontsize, direction='in')


        #final_figure
        fig.savefig(os.path.join(self.path_to_save, r'Optimisation_result_' + self.target + '.png'), dpi = 300, bbox_inches="tight")

        print('Saved:', 'Optimisation_result_' + self.target + '.png')


    def objective_plot(self, save=True):
        """
        Plot objective and corresponding evaluation plots

        args: None
        return: objective and evaluation plots
        """
        fig = plt.figure(figsize=(10, 10))
        _ = plot_objective(self.opt, n_points = 40) 
        
        if save:
            plt.savefig(self.path_to_save + 'plot_objective.png', dpi=500, bbox_inches='tight')
            
        plt.show()
        
        
        fig = plt.figure(figsize=(10, 10))
        _ = plot_evaluations(self.opt)
        
        if save:
            plt.savefig(self.path_to_save + 'plot_evaluations.png', dpi=500, bbox_inches='tight')
            
        plt.show()


    def objective_plot_adjust(self, sample_source, minimum, n_minimum_search=None, save=True):
        """
        Plot objective and corresponding evaluation plots

        args: None
        return: objective and evaluation plots
        """
        fig = plt.figure(figsize=(10, 10))
        _ = plot_objective(self.opt, n_points = 40, minimum=minimum, sample_source=sample_source, n_minimum_search=n_minimum_search) 
        
        if save:
            plt.savefig(self.path_to_save + 'plot_objective_adjusted.png', dpi=500, bbox_inches='tight')
        
        plt.show()
        

    def train_model(self):
        """
        Train model with optimal hyperparameters identified 

        args: None
        return: trained model
        """
        # Set model with optimal parameters 
        self.model = self.estimator

        for p, v in zip(self.hyperparameters, self.values):
            self.model.set_params(**{p: v})

        self.model.fit(self.sample_train[self.RFE_features], self.sample_train[self.target].values.ravel())

        return self.model


    def regression_plot(self, X, Y, min_value, max_value):
        """
        Show regression results; this function is recalled using 'evaluate()'

        args: 
        (a) X (type:list); true/observed target values
        (b) Y (type:list); predicted target values
        (c) min_value (type:int); min value to plot i.e. lower limit
        (d) max_value (type:int); max value to plot i.e. upper limit

        return: stats and figure of regression plot
        """
        # Figure
        plt.figure(figsize=(8, 8)) 

        # Predicted vs Actual
        plt.plot(X, Y, 'o', markersize=5, color='black', alpha=0.15)

        # line of best fit
        no_ticks = 10
        linear_fit = np.linspace(min_value, max_value, no_ticks)
        plt.plot(linear_fit, linear_fit*self.stats_results.params[1] + self.stats_results.params[0], '-', color='tab:blue') 

        # Ideal y=x 
        y = x = np.linspace(min_value, max_value, no_ticks)
        plt.plot(x, y, '--', color='red', alpha=0.8) 

        fontsize = 25
        plt.xlim([min_value, max_value])
        plt.ylim([min_value, max_value])
        plt.xlabel('True target value', fontsize=fontsize)
        plt.ylabel('Predicted target value', fontsize=fontsize)
        plt.tick_params(axis='both', which='both', labelsize=fontsize, direction="in")
        plt.rcdefaults()

        print('Linear fit has: ')
        print('m = ', self.stats_results.params[1])
        print('c = ', self.stats_results.params[0], '\n')

        plt.savefig(os.path.join(self.path_to_save, r'regression_plot_' + self.target + '.png'), dpi = 300, bbox_inches="tight")
        plt.show()

        print('Saved:', 'regression_plot_' + self.target + '.png')


    def confusion_matrix(self, target_names):
        """
        Generate confusion matrix plot 

        args: target_names (type:list); list of target classes
        return: conusion matrix plot
        """
        disp = ConfusionMatrixDisplay.from_estimator(
                                            self.model,
                                            self.sample_test[self.RFE_features],
                                            self.sample_test[self.target],
                                            display_labels=np.array(target_names, dtype='<U10'),
                                            cmap=plt.cm.Blues,
                                            normalize=None
                                            )
        
        fontsize = 18
        plt.tick_params(axis='both', which='major', labelsize=fontsize, direction='in')
        plt.savefig(os.path.join(self.path_to_save, r'Confusion_matrix_' + self.target + '.png'), dpi = 500, bbox_inches="tight")
        plt.show()

        print('Saved:', 'Confusion_matrix_' + self.target + '.png')


    def evaluate(self, strategy, *args, **kwargs):
        """
        Evaluate the ML model using out-of-sample test set

        args: 
        (a) strategy (type:str); averaging method e.g. 'micro', 'macro', 'weighted'
        (b*) target_names (type:list); list of target classes

        return: stats and plots of result
        """
        if self.problem == 'classification':

            self.target_names = kwargs.get('target_names')

            # Apply model onto test data
            self.y_test = self.sample_test[self.target]
            self.y_pred =  self.model.predict_proba(self.sample_test[self.RFE_features])
            self.y_pred_2 = self.model.predict(self.sample_test[self.RFE_features])

            # Evaluate metric scores
            print('1. The F-1 score of the model {}\n'.format(f1_score(self.y_test.ravel(), self.y_pred_2, average=strategy)))
            print('2. The recall score of the model {}\n'.format(recall_score(self.y_test.ravel(), self.y_pred_2, average=strategy)))
            print('3. Classification report \n {} \n'.format(classification_report(self.y_test.ravel(), self.y_pred_2, target_names=self.target_names)))
            print('4. Classification report \n {} \n'.format(multilabel_confusion_matrix(self.y_test.ravel(), self.y_pred_2)))
            print('5. Confusion matrix \n {} \n'.format(confusion_matrix(self.y_test.ravel(), self.y_pred_2)))
            print('6. Accuracy score \n {} \n'.format(accuracy_score(self.y_test.ravel(), self.y_pred_2)))
            print('7. Balanced accuracy score \n {} \n'.format(balanced_accuracy_score(self.y_test.ravel(), self.y_pred_2)))

            # Convert each row to 1 and 0 based on prob
            all_scores = self.y_pred
            all_scores_2 = np.zeros_like(all_scores)
            all_scores_2[np.arange(len(all_scores)), all_scores.argmax(1)] = 1

            # Get pretty conusion matrix
            self.confusion_matrix(self.target_names)


        elif self.problem == 'regression':

            adjusted = kwargs.get('adjusted')
            min_value = kwargs.get('min_value')
            max_value = kwargs.get('max_value')

            # Apply model onto test data
            self.y_test = self.sample_test[self.target]
            self.y_pred = self.model.predict(self.sample_test[self.RFE_features])
            self.id_index = self.sample_test.index.tolist()


            df_pred = pd.DataFrame(
                                    {'task_id': self.id_index, 
                                    str(self.target): self.y_test, 
                                    'pred_target': self.y_pred
                                    })

            # Create a column to eliminate negative values
            df_pred['pred_target'] = df_pred['pred_target']
            df_pred['adjusted_pred_target'] = df_pred['pred_target'].apply(lambda x: 0 if x < 0 else x)

            X = df_pred[self.target]

            if adjusted == True:
                Y = df_pred['adjusted_pred_target']
            else:
                Y = df_pred['pred_target'] 

            # Stats
            self.stats_results = sm.OLS(Y,sm.add_constant(X)).fit()

            print(self.stats_results.summary())

            print('MAE: ', mean_absolute_error(X, Y))
            print('MSE: ', mean_squared_error(X, Y))
            print('RMSE: ', mean_squared_error(X, Y, squared=False))
            print('R-squared: ', r2_score(X, Y))
            print('Max error: ', max_error(X, Y))
            print('Explained_variance_score: ', explained_variance_score(X, Y, multioutput='variance_weighted'))

            # Plot figure
            self.regression_plot(X, Y, min_value, max_value)



    def ROC(self, overall_performance, *args, **kwargs):
        """
        Generate ROC plot for the classification problem

        args: 
        (a) overall_performance (type:bool); whether to plot the overall average, where strategy determines the method of averaging
        (b*) strategy (type:str); averaging method e.g. 'micro', 'macro', 'weighted'
        (c*) positive_class (type:int) - index of positive class

        return: figure of ROC 
        """
        strategy = kwargs.get('strategy')
        positive_class = kwargs.get('positive_class')

        self.y_test = self.sample_test[self.target]
        self.y_pred =  self.model.predict_proba(self.sample_test[self.RFE_features])
        self.y_pred_2 = self.model.predict(self.sample_test[self.RFE_features])

        # Compute ROC curve and ROC area for each class
        self.fpr = dict()
        self.tpr = dict()
        self.n_classes = self.y_pred.shape[1]
        roc_auc = dict()

        self.y_test_2 = label_binarize(self.y_test, classes = list(range(self.n_classes)))

        # Binary
        if self.n_classes == 2:
            # Calculate ROC AUC score
            roc_auc_score_ = roc_auc_score(np.array(self.y_test.tolist()), self.y_pred[:, positive_class], average='macro')
            print('roc_auc_score:', roc_auc_score_)
            
            self.fpr, self.tpr, _ = roc_curve(self.y_test, self.y_pred[:, positive_class])
            roc_auc = auc(self.fpr, self.tpr)

            _, ax = plt.subplots(figsize=(8, 8), dpi=100)
            display = RocCurveDisplay(fpr=self.fpr, tpr=self.tpr).plot(ax=ax)
            ax.yaxis.get_major_ticks()[0].label1.set_visible(False)
            
            
        # Multiclass
        #################### Micro
        elif self.n_classes > 2:
            for i in range(self.n_classes):
                self.fpr[i], self.tpr[i], _ = roc_curve(self.y_test_2[:, i], self.y_pred[:, i])
                roc_auc[i] = auc(self.fpr[i], self.tpr[i])

            # Compute micro-average ROC curve and ROC area
            self.fpr["micro"], self.tpr["micro"], _ = roc_curve(self.y_test_2.ravel(), self.y_pred.ravel())
            roc_auc["micro"] = auc(self.fpr["micro"], self.tpr["micro"])

            #################### Macro
            # First aggregate all false positive rates
            all_fpr = np.unique(np.concatenate([self.fpr[i] for i in range(self.n_classes)]))

            # Then interpolate all ROC curves at this points
            mean_tpr = np.zeros_like(all_fpr)
            for i in range(self.n_classes):
                mean_tpr += np.interp(all_fpr, self.fpr[i], self.tpr[i])

            # Finally average it and compute AUC
            mean_tpr /= self.n_classes

            self.fpr["macro"] = all_fpr
            self.tpr["macro"] = mean_tpr
            roc_auc["macro"] = auc(self.fpr["macro"], self.tpr["macro"])

            # Plot all ROC curves
            fig = plt.figure(figsize=(8, 8))
            if overall_performance == True:
                if strategy == 'micro':
                    plt.plot(
                            self.fpr["micro"], self.tpr["micro"],
                            label='micro-average ROC (AUC = {0:0.3f})'
                                ''.format(roc_auc["micro"]),
                            color='tab:green', linestyle='-', linewidth=4
                            )

                if strategy == 'macro':
                    plt.plot(
                            self.fpr["macro"], self.tpr["macro"],
                            label='macro-average ROC (AUC = {0:0.3f})'
                                ''.format(roc_auc["macro"]),
                            color='tab:blue', linestyle='-', linewidth=4
                            )

            if overall_performance == False:
                # Individual class
                lw = 2
                colors = cycle(['aqua', 'darkorange', 'cornflowerblue'])
                for i, color in zip(range(self.n_classes), colors):
                    plt.plot(
                            self.fpr[i], self.tpr[i], color=color, lw=lw,
                            label='ROC curve of class {0} (AUC = {1:0.3f})'
                            ''.format(i, roc_auc[i])
                            )
        
            print('Average ROC AUC score, micro-averaged over all classes: {0:0.3f}'
                        .format(roc_auc_score(np.array(self.y_test_2.tolist()), self.y_pred, average='micro')))

            print('Average ROC AUC score, macro-averaged over all classes: {0:0.3f}'
                        .format(roc_auc_score(np.array(self.y_test_2.tolist()), self.y_pred, average='macro')))

            print('Average ROC AUC score, weighted-averaged over all classes: {0:0.3f}'
                        .format(roc_auc_score(np.array(self.y_test_2.tolist()), self.y_pred, average='weighted')))
        
        # Plot curves
        fontsize = 25
        lw=2

        plt.plot([0, 1], [0, 1], 'k--', lw=lw)
        plt.xlim([0, 1])
        plt.ylim([0, 1.01])
        plt.xlabel('False Positive Rate', fontsize=fontsize)
        plt.ylabel('True Positive Rate', fontsize=fontsize)
        plt.tick_params(axis='both', which='major', labelsize=fontsize, direction='in')
        #plt.legend(loc="lower right", fontsize=fontsize, framealpha=1)

        #final_figure
        plt.savefig(os.path.join(self.path_to_save, r'Receiver_operating_characteristic_curve_' + self.target + '.png'), dpi = 500, bbox_inches="tight")
        plt.show()

        print('Saved:', 'Receiver_operating_characteristic_curve_' + self.target + '.png')



    def DET(self, *args, **kwargs):
        """
        Generate DET plot for the classification problem

        args: strategy (type:str); averaging method e.g. 'micro', 'macro', 'weighted'
        return: figure of DET curve
        """
        strategy = kwargs.get('strategy')

        # Plot curves
        fontsize = 25
        linewidth = 2
        

        # Binary
        if self.n_classes == 2:
            _, ax = plt.subplots(figsize=(8, 8), dpi=100)

            fnr = 1 - self.tpr
            
            plt.plot(
                    fnr, self.fpr,
                    color='tab:blue', 
                    linestyle='-',
                    linewidth=linewidth
                    )
            
            ax.yaxis.get_major_ticks()[0].label1.set_visible(False)

        # Multiclass
        elif self.n_classes > 2:
            # Detection Error Trade-off Curve
            fnr_macro = 1 - self.tpr['macro']
            fnr_micro = 1 - self.tpr['micro']

            plt.figure(figsize = (8,8))
            if strategy == 'macro':
                plt.plot(
                        fnr_macro, self.fpr['macro'] ,
                        label='macro-average ERR',
                        color='tab:blue', 
                        linestyle='-',
                        linewidth=linewidth
                        )

            if strategy == 'micro':
                plt.plot(
                        fnr_micro, self.fpr['micro'] ,
                        label='micro-average ERR ',
                        color='tab:green', 
                        linestyle='-',
                        linewidth=linewidth
                        )

        lw=2
        
        plt.plot([0, 1], [0, 1], 'k--', lw=lw)
        plt.xlim([0, 1])
        plt.ylim([0, 1])
        plt.xlabel('False Negative Rate', fontsize=fontsize)
        plt.ylabel('False Positive Rate', fontsize=fontsize)
        plt.tick_params(axis='both', which='major', labelsize=fontsize, direction='in')
        #plt.legend(loc="upper right", fontsize=fontsize, framealpha=1)
    

        #final_figure
        plt.savefig(os.path.join(self.path_to_save, r'detection_error_tradeoff_curves_' + self.target + '.png'), dpi = 500, bbox_inches="tight")
    
        plt.show()

        print('Saved:', 'detection_error_tradeoff_curves_' + self.target + '.png')

    
    def PR(self, *args, **kwargs):
        """
        Generate PR curve for the classification problem

        args: None
        return: figure of PR curve
        """
        positive_class = kwargs.get('positive_class')

        self.y_test = self.sample_test[self.target]
        self.y_pred =  self.model.predict_proba(self.sample_test[self.RFE_features])
        self.y_pred_2 = self.model.predict(self.sample_test[self.RFE_features])
        
        

        # For each class
        n_classes = self.y_pred.shape[1]
        precision = dict()
        recall = dict()
        average_precision = dict()
        thresholds = dict()


        if self.n_classes == 2:
            # Calculate avg precision 
            average_precision = average_precision_score(self.y_test_2, self.y_pred[:, positive_class], average='macro')
            print('average_precision:', average_precision)
            
            # Plot PR curve
            _, ax = plt.subplots(figsize=(8, 8), dpi=100)
            prec, recall, _ = precision_recall_curve(self.y_test, self.y_pred[:, positive_class])
            pr_display = PrecisionRecallDisplay(precision=prec, recall=recall).plot(ax=ax)
            ax.yaxis.get_major_ticks()[0].label1.set_visible(False)


        elif self.n_classes > 2:
            # Multiclass
            self.y_test_2 = label_binarize(self.y_test, classes = list(range(n_classes))) 
                
            # For each class / for the top classifier
            for i in range(n_classes):
                precision[i], recall[i], _ = precision_recall_curve(self.y_test_2[:, i], self.y_pred[:, i])
                average_precision[i] = average_precision_score(self.y_test_2[:, i], self.y_pred[:, i])
                    
            precision["micro"], recall["micro"], thresholds['micro'] = precision_recall_curve(self.y_test_2.ravel(),self.y_pred.ravel())
                
            average_precision["micro"] = average_precision_score(self.y_test_2, self.y_pred, average="micro")
            average_precision["weighted"] = average_precision_score(self.y_test_2, self.y_pred, average="weighted")
            average_precision["macro"] = average_precision_score(self.y_test_2, self.y_pred, average="macro")
        
            print('Average precision score, micro-averaged over all classes: {0:0.3f}'
                        .format(average_precision["micro"]))

            print('Average precision score, macro-averaged over all classes: {0:0.3f}'
                        .format(average_precision["macro"]))

            print('Average precision score, weighted-averaged over all classes: {0:0.3f}'
                        .format(average_precision["weighted"]))

            #print('PR_AUC_micro: ', auc(recall["micro"], precision["micro"]))


            # Plot figure
            fig = plt.figure(figsize=(8, 8))

            fontsize = 25

            plt.step(
                    recall['micro'], precision['micro'], 
                    where='post', 
                    lw=2, 
                    color='tab:blue', 
                    label='Micro-averaged PR (AP = 0.995)'
                    )


            f_scores = np.linspace(0.2, 0.8, num=4)
            lines = []
            labels = []

            n = 0
            for f_score in f_scores:
                x = np.linspace(0.001, 1.0)
                y = f_score * x / (2 * x - f_score)
                l, = plt.plot(x[y >= 0], y[y >= 0], color='gray', alpha=0.2)
                
                #plt.annotate('f1={0:0.1f}'.format(f_score), xy=(0.9, y[45] + 0.02))

            # Location of the annotation
            x0 = [0.13, 0.26, 0.43, 0.67]
            y0 = [0.2, 0.4, 0.6, 0.8]
            n = 0
            fontsize2 = 14

            while n < len(x0):
                if n < 0:
                    plt.annotate('F1=' + str(y0[n]), xy=(x0[n], 0.99 + 0.02),fontsize=fontsize2)
                else:
                    plt.annotate('F1=' + str(y0[n]), xy=(x0[n], 0.99 + 0.02),fontsize=fontsize2)
                n = n + 1 


        lw=2
        labelsize = 25
        plt.plot([0, 1], [0, 1], 'k--', lw=lw)
        plt.xlabel('Recall',fontsize=labelsize)
        plt.ylabel('Precision',fontsize=labelsize)
        plt.ylim([0, 1.05])
        plt.xlim([0, 1.0])
        plt.tick_params(axis='both', which='major', labelsize=labelsize, direction='in')
        #plt.legend(fontsize=fontsize, loc="lower left", framealpha=1.0)

        #Save figure
        plt.savefig(os.path.join(self.path_to_save, r'precision_recall_' + self.target + '.png'), dpi = 500, bbox_inches="tight")
        
        plt.show()

        print('Saved:', 'precision_recall_' + self.target + '.png')


