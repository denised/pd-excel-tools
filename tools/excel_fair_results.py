import argparse
import os.path
import pathlib
import sys

import fair
import fair.RCPs
import matplotlib
import matplotlib.animation
import matplotlib.pyplot as plt
import matplotlib.style
import model.fairutil
import numpy as np
import tempfile
import pandas as pd
import solution.factory
import ui.color


def process_scenario(filename, scenario):
    sheet_name = 'Gtperyr_' + scenario
    raw = pd.read_excel(io=filename, sheet_name=sheet_name, header=None, index_col=0,
            dtype=object, skiprows=0, nrows=52, usecols='A:EF')
    years = raw.index[11:]
    solution_names = sorted(list(set(raw.iloc[5, 3:].dropna())))

    solutions = pd.DataFrame(0, index=range(1850, 2061), columns=solution_names)
    solutions.index.name = 'Year'
    sectors = {}
    prev_solution = None
    prev_sector = None
    for (_, col) in raw.iloc[:, 3:].iteritems():
        numeric = pd.to_numeric(col.iloc[11:], errors='coerce').fillna(0.0)
        if np.count_nonzero(numeric.to_numpy()) == 0:
            continue
        mechanism = col.iloc[3] if not pd.isna(col.iloc[3]) else 'Avoided'
        sector = col.iloc[4] if not pd.isna(col.iloc[4]) else prev_sector
        solution = col.iloc[5] if not pd.isna(col.iloc[5]) else prev_solution
        if mechanism == 'Avoided':
            numeric.iloc[0] = 0.0
        numeric.name = solution
        solutions[solution] += ((numeric / 1000.0) / 3.664)  # Mtons CO2 -> Gtons C
        sector_list = sectors.get(sector, [])
        sectors[sector] = sector_list + [solution]
        prev_solution = solution
        prev_sector = sector

    total = model.fairutil.baseline_emissions()
    _,_,T = fair.forward.fair_scm(emissions=total.values, useMultigas=False,
            r0=model.fairutil.r0, tcrecs=model.fairutil.tcrecs)
    baseline_T = pd.Series(T, index=total.index)
    temperature = pd.DataFrame(index=range(1850, 2061), columns=solution_names)
    temperature.index.name = 'Year'
    for solution, emissions in solutions.iteritems():
        total = model.fairutil.baseline_emissions()
        total = total.subtract(emissions.fillna(0.0), fill_value=0.0)
        _,_,T = fair.forward.fair_scm(emissions=total.values, useMultigas=False,
                r0=model.fairutil.r0, tcrecs=model.fairutil.tcrecs)
        df_T = pd.Series(T, index=total.index)
        temperature[solution] = df_T - baseline_T

    total = model.fairutil.baseline_emissions()
    emissions = solutions.sum(axis=1)
    temperature.insert(loc=len(temperature.columns), column="Baseline", value=baseline_T)
    total = total.subtract(emissions.fillna(0.0), fill_value=0.0)
    _,_,T = fair.forward.fair_scm(emissions=total.values, useMultigas=False,
                r0=model.fairutil.r0, tcrecs=model.fairutil.tcrecs)
    df_T = pd.Series(T, index=total.index)
    temperature.insert(loc=len(temperature.columns), column="Total", value=df_T.copy())

    outfile = os.path.splitext(os.path.basename(filename))[0] + '_Temperature_' + scenario + '.csv'
    temperature.to_csv(outfile, float_format='%.3f')

    return (solutions, sectors)


def legend_no_duplicates(ax):
    handle, label = ax.get_legend_handles_labels()
    unique = [(h, l) for i, (h, l) in enumerate(zip(handle, label)) if l not in label[:i]]
    ax.legend(*zip(*unique), loc='upper left', frameon=False)


def animate(frame, ax, total, lines, emissions):
    (sector_num, offset) = divmod(frame, 50)
    (sector, df_T) = emissions[sector_num]
    color = ui.color.get_sector_color(sector)
    if offset == 0:
        zorder = 40 - sector_num
        line, = ax.plot([], [], color=color, label=sector, zorder=zorder)
        lines[sector] = line
        legend_no_duplicates(ax)
    else:
        line = lines[sector]

    if offset <= 30:
        end = 2020 + offset
        line.set_data(df_T.loc[2020:end].index.values, df_T.loc[2020:end].values)
        if sector_num == 0:
            _,_,T = fair.forward.fair_scm(emissions=total.values, useMultigas=False,
                    r0=model.fairutil.r0, tcrecs=model.fairutil.tcrecs)
            prev = pd.Series(T, index=fair.RCPs.rcp45.Emissions.year)
        else:
            (_, prev) = emissions[sector_num - 1]
        ax.fill_between(x=df_T.loc[2020:end].index.values, y1=prev.loc[2020:end].values,
                y2=df_T.loc[2020:end].values, color=color)


def produce_animation(solutions, sectors, filename):
    sector_gtons = pd.DataFrame()
    for sector, solution_list in sectors.items():
        sector_gtons.loc[:, sector] = solutions.loc[:, solution_list].sum(axis=1)

    total = model.fairutil.baseline_emissions()
    remaining = total.copy()
    sectors = sector_gtons.sort_values(axis='columns', by=2050, ascending=False).columns
    emissions = []
    for sector in sectors:
        remaining = remaining.subtract(sector_gtons[sector], fill_value=0.0)
        _,_,T = fair.forward.fair_scm(emissions=remaining.values, useMultigas=False,
                r0=model.fairutil.r0, tcrecs=model.fairutil.tcrecs)
        df_T = pd.Series(T, index=remaining.index)
        emissions.append((sector, df_T))

    fig = plt.figure()
    ax = fig.add_subplot()
    ax.set_ylabel(u'°C');
    _,_,T = fair.forward.fair_scm(emissions=total.values, useMultigas=False, r0=model.fairutil.r0,
            tcrecs=model.fairutil.tcrecs)
    df_T = pd.Series(T, index=fair.RCPs.rcp45.Emissions.year)
    ax.plot(df_T.loc[2005:2050].index.values, df_T.loc[2005:2050].values,
            color='black', label='Baseline', zorder=50)
    legend_no_duplicates(ax)

    ffmpeg = matplotlib.animation.writers['ffmpeg']
    writer = ffmpeg(fps=15, bitrate=-1,
            metadata={'title':'Play the Whole Field', 'subject':'Climate Change Solutions',
                'copyright':'Copyright 2020 Project Drawdown'},
            extra_args=['-tune', 'animation'],)

    lines = {}
    frames = len(emissions) * 50
    anim = matplotlib.animation.FuncAnimation(fig=fig, func=animate, interval=10, frames=frames,
            fargs=(ax, total, lines, emissions), repeat=False)
    anim.save(filename, writer=writer)


def process_ghgs(filename):
    for scenario in ['PDS1', 'PDS2', 'PDS3']:
        print(f"{scenario} CSV")
        (solutions, sectors) = process_scenario(filename=filename, scenario=scenario)
        print(f"{scenario} animation")
        animfile = os.path.splitext(os.path.basename(filename))[0] + '_' + scenario + '.mp4'
        produce_animation(solutions=solutions, sectors=sectors, filename=animfile)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Produce FaIR results from Drawdown emissions data.')
    parser.add_argument('--excelfile', help='Excel filename to process',
            default='CORE-Global_GHG_Accounting_12-1-2019.xlsm')
    args = parser.parse_args(sys.argv[1:])

    matplotlib.style.use('ggplot')
    process_ghgs(filename=args.excelfile)
