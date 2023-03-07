import pandas as pd
import numpy as np
import petab
import re
import petab.models

from pathlib import Path

model_dir = Path(__file__).parent
model_name = 'Smith_BMCSystBiol2013'
source_dir = model_dir / "source"

simulations = dict()
data = dict()
# -- figure 1 --
simfiles = {
    'fig1': 'm8b2_rapie.6-t60.txt',
    'fig2A': 'm8b2_rapie.6-t60.txt',
    # used in 2B 2E 3A figures, assuming equal name means equal data
    'base': 'm8b2_rapi.6-insscan.txt',
    'fig2E': 'm8b2_rapi.6-insscan-nox0.txt',
    'fig2F': 'pj.6-t60-scanextROS-2SOD.txt',
    'fig2H': 'm8b2_rapijf.6.InsROS_out.txt',
    'fig3A_left': 'm8b2_rapi_sensitized-insscan.txt',
    'fig3A_right': 'm8b2_rapijfe.6.fasting-t3000.txt',
}

# -- figure 2 data --
data['pi3k_fig2B'] = pd.read_csv(source_dir / 'stagsted_93_fig3.txt', sep='\s+', skiprows=range(3))
data['pi3k_fig2B']['Time'] = 15  # 15 min according to simulation data (m8b2_rapi.6-insscan.txt)
data['ins_fig2B'] = pd.read_csv(source_dir / 'stagsted_93_fig1_boundi.txt', sep='\s+', skiprows=range(2))
data['ins_fig2B']['Time'] = 15  # 15 min according to simulation data (m8b2_rapi.6-insscan.txt)
data['glut4_fig2B'] = pd.read_csv(source_dir / 'stagsted_93_fig1_glut.txt', sep='\s+', skiprows=range(2))
data['glut4_fig2B']['Time'] = 15  # 15 min according to simulation data (m8b2_rapi.6-insscan.txt)
data['p_irs_fig2C'] = pd.read_csv(source_dir / 'cedersund_irs_p_fig1c.dat.txt', sep='\t')
data['ptp1b_fig2D'] = pd.read_csv(source_dir / 'mahadev_01b_fig2.txt', sep='\t', skiprows=range(1))

# -- figure 3 data --
data['gluc_fig3B'] = pd.read_csv(source_dir / 'archuleta_09_fig1.txt', sep='\s+', skiprows=range(3))
data['sod2_fig3C'] = pd.read_csv(source_dir / 'essers_emboj_04_fig4b.txt', sep='\s+', skiprows=range(2))
data['sod2_fig3C']['Time'] = 16 * 60  # 16h according to comment in source data, confirmed in panel in manuscript

for figname, simfile in simfiles.items():
    simulations[figname] = pd.read_csv(source_dir / simfile, sep='\t')

# cleanup
for df in list(simulations.values()) + list(data.values()):
    df.dropna(axis=0, how='all', inplace=True)
    df.dropna(axis=1, how='all', inplace=True)

# extracted from R scripts (for panels/figures)
data_mappings = {
    'pi3k_fig2B': 'base',
    'ins_fig2B': 'base',
    'glut4_fig2B': 'base',
    'p_irs_fig2C': 'fig2A',
    'ptp1b_fig2D': 'fig2A',
    # `m8b2_rapijf.6.InsROS-t1440_out.txt`, hopefully the same as `m8b2_rapijf.6.InsROS_out.txt` with diff timepoints?
    'gluc_fig3B': 'fig2H',
    'sod2_fig3C': 'fig2H',
}

for simname, simulation in simulations.items():
    simulation['dataset'] = simname
df_sim = pd.concat(simulations.values(), ignore_index=True)
for dataname, dataset in data.items():
    dataset['dataset'] = dataname
df_data = pd.concat(data.values(), ignore_index=True)

# potentially missing datasets:
# - Lee 1998 referenced in text about estimation, but unclear how/which dataset was used
# - Lee 2002 not referenced in text about estimation
# - Seo 2005 not references in text about estimation
# - Kops 2002 not references in text about estimation
# probably used to infer parameter values (is referenced in parameter table):
# - Adimora 2010
# - Greene 2003
# - Ambrogini 2010
# - Bloch-Damti 2006
# - Liu 2007
# omitted as analysis was to check for stable cycles under physiological conditions
# - Frayn 1996

# use BIOMODELS model version instead of original model version as it's a bit more cleaned up and already went through
# one round of curation
model_file = source_dir / 'BIOMD0000000474_url.xml'
import libsbml as sbml
# read model using libsbml
sbml_reader = sbml.SBMLReader()
sbml_document = sbml_reader.readSBMLFromFile(str(model_file))
sbml_model = sbml_document.getModel()

sbml_model.setName(model_name)
sbml_model.setId(model_name)

# add event to end insulin stimulation
tt = sbml_model.createParameter()
tt.setId('t_ins')
tt.setValue(15)
tt.setConstant(True)
event = sbml_model.createEvent()
event.setId('insulin_stimulation')
trigger = event.createTrigger()
trigger.setMath(sbml.parseL3Formula('time >= t_ins'))
event.setTrigger(trigger)
a = event.createEventAssignment()
a.setVariable('Ins')
a.setMath(sbml.parseL3Formula('0.0'))
event.addEventAssignment(a)
sbml_model.addEvent(event)

# confirmed by inspection of simfiles, time of insulin stimulation
t_ins = {
    figname: 15.0 if 'e.6-t60' in simfile else df_sim.Time.max()*2
    for figname, simfile in simfiles.items()
}

# simulation data files have endings 'rapi', 'rapie', 'rapijf', 'rapijfe', which likely corresponds to
# different model compositions. looking at the shorthand sbml files in the supplementary material suggests the
# following mapping:
# - r: m8b2_recep.6.mod
# - a: m8b2_akt.6.mod
# - p: m8b2_phosph.6.mod
# - i: m8b2_ins.6.mod
# - j: m8b2_jnk.6.mod
# - f: m8b2_foxo.6.mod
# - e: m8b2_events.ins5d.mod (insulin events, giant mess, at least in the ins5d case)

# this means that for some of the simulations, we need to disable jnk/foxo components. To emulate this, we can
# add indicator variables to the rate laws of the respective reactions

# for jnk module, these are the following reactions:
# - R42f, R42r, R43f, R43r, R32f, R32r
i_j = sbml_model.createParameter()
i_j.setId('indicator_jnk')
i_j.setValue(0)
i_j.setConstant(True)

for r_id in ('R42f', 'R42r', 'R43f', 'R43r', 'R32f', 'R32r'):
    kin_law = sbml_model.getReaction(r_id).getKineticLaw()
    formula = sbml.formulaToL3String(kin_law.getMath())
    formula += ' * indicator_jnk'
    kin_law.setMath(sbml.parseL3Formula(formula))

indicator_jnk = {
    figname: 'j' in simfile.split('.')[0].split('_')[1]
    if simfile.startswith('m8b2') else True
    for figname, simfile in simfiles.items()
}


# for foxo, these are the folling reactions:
# - R100 - R406
i_f = sbml_model.createParameter()
i_f.setId('indicator_foxo')
i_f.setValue(0)
i_f.setConstant(True)

for r_num in range(100, 407):
    kin_law = sbml_model.getReaction(f'R{r_num}').getKineticLaw()
    formula = sbml.formulaToL3String(kin_law.getMath())
    formula += ' * indicator_foxo'
    kin_law.setMath(sbml.parseL3Formula(formula))

indicator_foxo = {
    figname: 'f' in simfile.split('.')[0].split('_')[1]
    if simfile.startswith('m8b2') else False
    for figname, simfile in simfiles.items()
}

pnames = [
    p.id for p in sbml_model.getListOfParameters()
    if p.id not in (
        'navo', 'molec_per_fm', 'membrane_area', 'k_ros_perm', 't_ins', 'indicator_jnk', 'indicator_foxo',
        'k4', 'kminus4', 'k_irs1_basal_syn'
    )
    and sbml_model.getAssignmentRule(p.id) is None
]

# iconsistent parameter values:
# - k4: 3.33e-4 (all data except 3A) and 3.33e-2 (as in manuscript)
# - kminus4: 0.003 (all data except 3A) and 0.3 (as in manuscript)
# - k_irs1_basal_syn: 130 (all data except 3A) and 260 (as in manuscript)

k4 = {
    figname: simulations[figname]['k4'].unique()[0] if 'k4' in simulations[figname] else 0.0
    for figname in simfiles.keys()
}
kminus4 = {
    figname: simulations[figname]['kminus4'].unique()[0] if 'kminus4' in simulations[figname] else 0.0
    for figname in simfiles.keys()
}
k_irs1_basal_syn = {
    figname: simulations[figname]['k_irs1_basal_syn'].unique()[0] if 'k_irs1_basal_syn' in simulations[figname] else 0.0
    for figname in simfiles.keys()
}
for par in ['k4', 'kminus4', 'k_irs1_basal_syn']:
    for figname in simfiles.keys():
        if par not in simulations[figname].columns:
            continue
        assert len(simulations[figname][par].unique()) == 1

p_nominal = {
    p: df_sim[p].dropna().values[0]
    for p in pnames
    if len(df_sim[p].dropna().unique()) == 1
}
for p in pnames:
    assert p in p_nominal

# cyto_vol, cellsurf_vol, both 1.0, probably fine.
# cytoplasm and cellsurface compartments have correct size (not parameterized though) and appear in equations

# k14, kminus14, kcat82, Km82: fine, not used in the model
# sc_pip, sc_ros: fine, scaling factors
# IRp: probably refers to IRSp?

# notes:
# k2psp is named kpsp2 in the manuscript
# ros_perm is 7.8e8 in the paper, but 7.4e7 in the txt
# k42f is 2.5e-4 in the paper, 5e-5 in the txt

# text: following parameters were estimated from data:
# k1, kminus1 (stagsted, fig1)
# k7, kminus7 (cedersund)
# k8, kminus8 (stagsted, fig3)

# k30f, k30r, k35f [19 (Mahadev 2001), 58 (Lee 1998)]

# effect of ROS on activation of JNK and IKK (k32f, k32r, k42f, k42r, k43f, k43r, based on table in manuscript)  essers

# SOD2 and InR transcriptional parameter were tuned such that stable cycles appear

estimated_parameters = [
    'k1', 'kminus1', 'k7', 'kminus7a', 'kminus7b', 'k8', 'kminus8', 'k30f', 'k30r', 'k35f', 'k32f', 'k32r', 'k42f',
    'k42r', 'k43f', 'k43r',
]
for p in estimated_parameters:
    assert p in p_nominal

parameters = [
    {
        petab.PARAMETER_ID: p,
        petab.PARAMETER_SCALE: petab.LOG10,
        petab.LOWER_BOUND: val / 100,
        petab.UPPER_BOUND: val * 100,
        petab.NOMINAL_VALUE: val,
        petab.ESTIMATE: int(p in estimated_parameters),
    } for p, val in p_nominal.items()
]

obs_names = [
    r.getVariable() for r in sbml_model.getListOfRules()
]

for o in obs_names:
    assert o in df_sim.columns

# for comparison against simulations
observables_test = [
    {
        petab.OBSERVABLE_ID: f'{o.replace("[", "_").replace(".","_")}_obs',
        petab.OBSERVABLE_FORMULA:
            # convert all species from concentration to amount
            f'{o} * {sbml_model.getCompartment(sbml_model.getSpecies(o).getCompartment()).getSize()}'
            if sbml_model.getSpecies(o) is not None
            else re.match('Compartments\[([\w]+)\.Volume', o).group(1)
            if re.match('Compartments\[([\w]+)\.Volume', o)
            else o
        ,
        petab.NOISE_FORMULA: '1.0',
    } for o in df_sim.columns
    if o not in pnames + ['dataset', 'Time']
]

observables = []

obs_def = (
    # figure 2B: PI3K https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig2/B/plotB.R 17, 29-40
    ('sc_PI3K',    'IRS1_TyrP_PI3K',      'PI3K_activity',          '2B'),
    # figure 2B: GLUT https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig2/B/plotB.R 21, 43-56
    ('sc_GLUT_2B', 'cellsurface_GLUT4',   'Glucose_uptake',         '2B'),
    # figure 2B: BINS https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig2/B/plotB.R 25, 60-73
    ('sc_BINS',    'InR_bound',           'Cell_Bound_Ins',         '2B'),
    # figure 2C: IRS1 https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig2/C/plotC.R
    ('sc_PIRS',    'IRS1_TyrP',           'IRSYp',                  '2C'),
    # figure 2D: PTP https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig2/D/plotD.R
    ('sc_PTP',     'PTP1B_plus_PTP1B_ox', 'PTP_activ',              '2D'),       # initial value normalized
    # figure 3B: GLUT https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig3/B/plotB.R
    ('sc_GLUT_3B', 'cellsurface_GLUT4',   'Glucose_uptake',         '3B'),
    # figure 3C: SOD2 https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig3/C/plotC.R 31
    ('sc_SOD2',    'cytoplasm_SOD2',      'MnSOD_fold_induction',   '3C'),  # initial value normalized
    # figure 3C: FOXO1 https://github.com/graham1034/Smith2012_insulin_signalling/blob/master/fig3/C/plotC.R 32
    ('sc_FOXO1',   'Foxo1_all',           'FOXO4',                  '3C'),  # initial value normalized
)

# for fitting to data
# notes: always use scaling factors instead of normalizing with max/initial value
for scale_factor, assignment_variable, data_variable, figure in obs_def:
    observables.append({
        petab.OBSERVABLE_ID: f'{data_variable}__{figure}',
        petab.OBSERVABLE_FORMULA: f'{scale_factor} * {assignment_variable}',
        petab.NOISE_FORMULA: '1.0',
    })
    parameters.append({
        petab.PARAMETER_ID: scale_factor,
        petab.PARAMETER_SCALE: petab.LOG10,
        petab.LOWER_BOUND: 1e-4,
        petab.UPPER_BOUND: 1e4,
        petab.NOMINAL_VALUE: 1.0,
        petab.ESTIMATE: 1,
    })
    assert assignment_variable in df_sim.columns
    assert assignment_variable in obs_names or sbml_model.getSpecies(assignment_variable) is not None
    assert data_variable in df_data.columns

conditions = []
measurements = []

# set initializations
for x in sbml_model.getListOfSpecies():
    assert x.id in df_sim.columns

    # set via conditions
    if x.id in ['Ins', 'extracellular_ROS', 'JNK', 'JNK_P', 'IKK', 'IKK_P', 'DUSP', 'DUSP_ox']:
        continue

    sel = df_sim.loc[df_sim.Time == 0.0, x.id].dropna()
    assert len(sel.unique()) == 1
    assert x.getInitialAmount() == sel.values[0]


df_data.Insulin.fillna(0.0, inplace=True)
df_data.H2O2.fillna(0.0, inplace=True)
data_cols = np.unique([obs[petab.OBSERVABLE_ID].split('__')[0] for obs in observables])
for (insconc, dataset, rosconc), df in df_data.groupby(['Insulin', 'dataset', 'H2O2']):
    # group: (Insulin, dataset, Time, H2O@)
    # df: all rows with this

    panel = dataset[-2:]

    sim = simulations[data_mappings[dataset]]
    m = df.melt(
        id_vars=['Time'],
        value_vars=data_cols,
        var_name=petab.OBSERVABLE_ID,
        value_name=petab.MEASUREMENT
    ).dropna(axis=0, subset=[petab.MEASUREMENT])
    m.rename(columns={'Time': petab.TIME}, inplace=True)
    m[petab.OBSERVABLE_ID] = m[petab.OBSERVABLE_ID] + '__' + dataset[-2:]
    condition_id = f'figure{panel}__{rosconc}__{insconc}'.replace('.', '_').replace('-', 'm')
    m[petab.SIMULATION_CONDITION_ID] = condition_id
    measurements.append(m)

    # Fig 2B: Insulin maps to insconc
    # Fig 2C/2D: only time?
    # Fig 3B: Insulin "maps" to insconc (5-->0.0, 5e4-->5.0), H2O2 "maps" to extracellular_ROS (rosconc) (0-->0.0, 5e4-->60)
    if panel == '3B':
        insconc = {0.0: 5, 5.0: 5e4}.get(insconc)
        rosconc = {0.0: 0, 60.0: 5e4}.get(rosconc)
    # maps: sim --> data
    # Fig 3C: H2O2 maps to extracellular_ROS*2 (rosconc ?)
    if panel == '3B':
        rosconc = rosconc / 2

    # the R scripts use `insconc`, which is computed using an assignment rule (concentration), instead of
    # `Ins`, which is a species (with amounts?). To use values for initialization, we need to convert:
    #
    # insconc = (Ins [species] * extracellular [compartment]) / (navo [parameter] * vextracellular [parameter])
    # Ins = insconc * (navo * vextracellular) / extracellular
    #

    navo = sbml_model.getParameter('navo').getValue()
    vextracellular = sbml_model.getParameter('vextracellular').getValue()

    v_ins = sbml_model.getCompartment(sbml_model.getSpecies('Ins').getCompartment()).getSize()
    v_ros = sbml_model.getCompartment(sbml_model.getSpecies('extracellular_ROS').getCompartment()).getSize()

    if panel in ['3B', '3C']:
        # Ins/ins is the other way around
        Ins = insconc / v_ins
        insconc = Ins * v_ros / (navo * vextracellular)
    else:
        Ins = insconc * (navo * vextracellular) / v_ins

    Ros = rosconc / v_ros

    # note that the simulation table likely reports Ins as amount, not concentration
    # so we have to multiply by extracellular volume to get the amount

    # check we are actually using the same values as in the supplementary material
    # 2B + ins=1e-14/5e-8 not included in simulations/plot :shrug:

    # we want Ins in concentrations, but simulations are in "amounts" (still floats ...)
    # so we need to multiply with the respective compartment size
    if panel not in ['2B', '3C']:
        assert np.isclose(insconc, sim.insconc.unique(), atol=0, rtol=1e-2).any()
        assert np.isclose(Ins * v_ins, sim.Ins.unique(), atol=0, rtol=1e-2).any()

    if panel not in ['3B', '3C']:
        assert Ros * v_ros in sim.extracellular_ROS.unique()

    if panel == '2B' and insconc != 1e-14:
        assert insconc < sim.insconc.max()
        assert insconc > sim.insconc.min()
        assert Ins * v_ins < sim.Ins.max()
        assert Ins * v_ins > sim.Ins.min()

    if condition_id not in (c[petab.CONDITION_ID] for c in conditions):
        conditions.append({
            petab.CONDITION_ID: condition_id,
            'extracellular_ROS': rosconc,
            'Ins': Ins,
            't_ins': t_ins[data_mappings[dataset]],
            'indicator_jnk': float(indicator_jnk[data_mappings[dataset]]),
            'indicator_foxo': float(indicator_foxo[data_mappings[dataset]]),
            'k4': k4[data_mappings[dataset]],
            'kminus4': kminus4[data_mappings[dataset]],
            'k_irs1_basal_syn': k_irs1_basal_syn[data_mappings[dataset]],
        })

measurements_test = []
conditions_test = []

for (dataset, rosconc, sod2, nox, e2f1), df in df_sim.groupby([
    'dataset', 'extracellular_ROS', 'cytoplasm_SOD2', 'NOX_total', 'E2F1'
], dropna=False):
    if df.Time.min() < t_ins[dataset]:
        single_ins = len(df.loc[df.Time < t_ins[dataset], 'Ins'].unique()) == 1
        insconc = df.loc[df.Time < t_ins[dataset], 'Ins'].values[0]

    else:
        assert len(df.loc[:, 'Ins'].unique()) == 1
        single_ins = True
        insconc = df.loc[:, 'Ins'].values[0]

    if single_ins:
        conditions_ins = ((insconc, df),)
    else:
        conditions_ins = df.groupby('Ins')

    for insconc, df_ins in conditions_ins:
        m = df_ins.melt(
            id_vars=['Time'],
            value_vars=[c for c in df.columns if c != 'Time'],
            var_name=petab.OBSERVABLE_ID,
            value_name=petab.MEASUREMENT
        ).dropna(axis=0, subset=[petab.MEASUREMENT])
        m.rename(columns={'Time': petab.TIME}, inplace=True)
        m.loc[:, petab.OBSERVABLE_ID] = m[petab.OBSERVABLE_ID].apply(
            lambda obs_id: obs_id.replace('[', '_').replace('.', '_') + '_obs'
        )
        m = m.loc[m[petab.OBSERVABLE_ID].isin([o[petab.OBSERVABLE_ID] for o in observables_test]), :]
        condition_id = f'{dataset}_{rosconc}__{insconc}__{sod2}__{nox}'.replace('.', '_').replace('-', 'm')
        m.loc[:, petab.SIMULATION_CONDITION_ID] = condition_id

        assert len(m[petab.OBSERVABLE_ID].unique()) * len(m[petab.TIME].unique()) == len(m)

        measurements_test.append(m)

        v_ins = sbml_model.getCompartment(sbml_model.getSpecies('Ins').getCompartment()).getSize()
        v_ros = sbml_model.getCompartment(sbml_model.getSpecies('extracellular_ROS').getCompartment()).getSize()
        v_sod = sbml_model.getCompartment(sbml_model.getSpecies('cytoplasm_SOD2').getCompartment()).getSize()
        # NOX_total = NOX_inact + NOX_act + NOX, so we can't assign that, looking at t==0, it looks like NOX_inact was
        # assigned
        v_nox = sbml_model.getCompartment(sbml_model.getSpecies('NOX_inact').getCompartment()).getSize()
        v_e2f1 = sbml_model.getCompartment(sbml_model.getSpecies('E2F1').getCompartment()).getSize()

        if condition_id not in (c[petab.CONDITION_ID] for c in conditions_test):
            conditions_test.append({
                petab.CONDITION_ID: condition_id,
                'extracellular_ROS': rosconc / v_ros,
                'Ins': insconc / v_ins,
                'cytoplasm_SOD2': sod2 / v_sod,
                'NOX_inact': nox / v_nox,
                'E2F1': e2f1 / v_e2f1,
                't_ins': t_ins[dataset],
                'indicator_jnk': float(indicator_jnk[dataset]),
                'indicator_foxo': float(indicator_foxo[dataset]),
                'k4': k4[dataset],
                'kminus4': kminus4[dataset],
                'k_irs1_basal_syn': k_irs1_basal_syn[dataset],
            })
observable_table = pd.DataFrame(observables).set_index(petab.OBSERVABLE_ID)
observable_table_test = pd.DataFrame(observables_test).set_index(petab.OBSERVABLE_ID)
parameter_table = pd.DataFrame(parameters).set_index(petab.PARAMETER_ID)
parameter_table_test = parameter_table.loc[
    [par_id for par_id in parameter_table.index if not par_id.startswith('sc_')], :
]
condition_table = pd.DataFrame(conditions).set_index(petab.CONDITION_ID)
condition_table_test = pd.DataFrame(conditions_test).set_index(petab.CONDITION_ID)
measurement_table = pd.concat(measurements)
measurement_table_test = pd.concat(measurements_test)

# derive scaling factors
for dataset, df in df_data.groupby(['dataset']):
    sim = simulations[data_mappings[dataset]]
    scaling_factors = {
        obs[0]: (obs[1], obs[2]) for obs in obs_def
        if dataset.endswith(obs[3]) and df[obs[2]].any()
    }
    for sc, (sim_id, data_id) in scaling_factors.items():
        vol = sbml_model.getCompartment(
            sbml_model.getSpecies(sim_id).getCompartment()
        ).getSize()
        parameter_table.loc[
            sc, petab.NOMINAL_VALUE
        ] = vol / sim[sim_id].max() * df[data_id].max()

petab_problem = petab.Problem(
    model=petab.models.sbml_model.SbmlModel(
        sbml_model=sbml_model,
        sbml_reader=sbml_reader,
        sbml_document=sbml_document,
    ),
    condition_df=condition_table,
    measurement_df=measurement_table,
    observable_df=observable_table,
    parameter_df=parameter_table,
)

petab.lint_problem(petab_problem)

petab_problem_test = petab.Problem(
    model=petab.models.sbml_model.SbmlModel(
        sbml_model=sbml_model,
        sbml_reader=sbml_reader,
        sbml_document=sbml_document,
    ),
    condition_df=condition_table_test,
    measurement_df=measurement_table_test,
    observable_df=observable_table_test,
    parameter_df=parameter_table_test,
)

petab.lint_problem(petab_problem_test)

petab_problem.to_files(
    model_file=f'model_{model_name}.xml',
    observable_file=f'observables_{model_name}.tsv',
    parameter_file=f'parameters_{model_name}.tsv',
    condition_file=f'experimentalCondition_{model_name}.tsv',
    measurement_file=f'measurementData_{model_name}.tsv',
    yaml_file=f'{model_name}.yaml',
    prefix_path=model_dir,
    relative_paths=True,
)

petab_problem_test.to_files(
    model_file=f'model_{model_name}.xml',
    observable_file=f'observables_{model_name}_test.tsv',
    parameter_file=f'parameters_{model_name}.tsv',
    condition_file=f'experimentalCondition_{model_name}_test.tsv',
    measurement_file=f'measurementData_{model_name}_test.tsv',
    yaml_file=f'{model_name}_test.yaml',
    prefix_path=model_dir / 'sim_test',
    relative_paths=True,
)
