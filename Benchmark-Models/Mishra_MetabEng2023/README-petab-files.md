```python

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import cm

from matplotlib import cm  # Import cm for colormaps
import matplotlib.pyplot as plt
from sklearn.metrics import r2_score, mean_squared_error


def plot_measurements_vs_simulation(simulation_df, measurement_df, output_file=None):
    """
    Generates a logarithmic scatter plot comparing measurements and simulations, 
    with R² and MSE displayed on the plot.

    Parameters:
        simulation_df (pd.DataFrame): DataFrame containing simulation data.
        measurement_df (pd.DataFrame): DataFrame containing measurement data.
        output_file (str, optional): If provided, saves the plot to this file. Defaults to None.

    Returns:
        None
    """
    # Merge the dataframes on relevant columns
    df_merged = pd.merge(
        pd.DataFrame(simulation_df),
        pd.DataFrame(measurement_df),
        on=['observableId', 'simulationConditionId', 'time', 'datasetId']
    )
    
    # Modify datasetID
    df_merged['datasetId'] = df_merged['datasetId'].str.extract(r'^[^_]*_([^_]*)_')[0]
    
    # Map unique colors to each datasetId
    unique_datasets = df_merged['datasetId'].unique()
    colors = colormaps['tab10']  # Use the updated colormap API
    color_list = [colors(i) for i in range(len(unique_datasets))]

    # Plotting
    plt.figure(figsize=(8, 8))
    plt.xscale('log')
    plt.yscale('log')

    for i, dataset in enumerate(unique_datasets):
        subset = df_merged[df_merged['datasetId'] == dataset]
        plt.scatter(subset['measurement'], subset['simulation'], color=color_list[i], label=dataset)

    # Calculate R² and MSE
    r2 = r2_score(df_merged['measurement'], df_merged['simulation'])
    mse = mean_squared_error(df_merged['measurement'], df_merged['simulation'])

    # Add R² and MSE to the plot
    x_min, x_max = df_merged['measurement'].min(), df_merged['measurement'].max()
    plt.plot([x_min, x_max], [x_min, x_max], 'k--')
    plt.text(
        x_min * 1.2, x_max / 2,
        f"$R^2$: {r2:.3f}\nMSE: {mse:.3e}",
        fontsize=10, bbox=dict(facecolor='white', alpha=0.8, edgecolor='gray')
    )

    # Add labels and legend
    plt.xlabel("Measurement (log scale)")
    plt.ylabel("Simulation (log scale)")
    plt.legend(title="Dataset ID")
    plt.show()
    
    # Show or save the plot
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
    else:
        plt.show()

        
# Assuming `simulation_df` and `measurement_df` are predefined dataframes
plot_measurements_vs_simulation(simulation_df, measurement_df)

# To save the plot instead of showing it
plot_measurements_vs_simulation(simulation_df, measurement_df, output_file="measurements_vs_simulation.png")


```
