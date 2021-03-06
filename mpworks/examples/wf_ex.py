from collections import defaultdict
from pprint import pprint
from custodian.vasp.handlers import VaspErrorHandler, FrozenJobErrorHandler, MeshSymmetryErrorHandler, NonConvergingErrorHandler
from custodian.vasp.jobs import VaspJob
from fireworks.core.firework import FireWork, Workflow
from fireworks.utilities.fw_utilities import get_slug
from mpworks.examples.firetasks_ex import VaspCustodianTaskEx, VaspToDBTaskEx
from mpworks.firetasks.vasp_io_tasks import VaspWriterTask, VaspCopyTask
from mpworks.firetasks.vasp_setup_tasks import SetupStaticRunTask
from pymatgen import Composition, Lattice
from pymatgen.core.structure import Structure
from pymatgen.io.vaspio_set import MPGGAVaspInputSet

__author__ = 'Anubhav Jain'
__copyright__ = 'Copyright 2013, The Materials Project'
__version__ = '0.1'
__maintainer__ = 'Anubhav Jain'
__email__ = 'ajain@lbl.gov'
__date__ = 'Oct 03, 2013'


def get_name(structure, task_type):
    return get_slug(structure.formula + '--' + task_type)


def structure_to_wf(structure):
    """
    This method starts with a Structure object and creates a Workflow object
    The workflow has two steps - a structure relaxation and a static run
    :param structure:
    :return:
    """
    fws = []  # list of FireWorks to run
    connections = defaultdict(list)  # dependencies between FireWorks

    # generate VASP input objects for 1st VASP run - this is put in the FW spec
    mpvis = MPGGAVaspInputSet(user_incar_settings={'NPAR': 2})
    incar = mpvis.get_incar(structure)
    poscar = mpvis.get_poscar(structure)
    kpoints = mpvis.get_kpoints(structure)
    potcar = mpvis.get_potcar(structure)

    # serialize the VASP input objects to the FW spec
    spec = {}
    spec['vasp'] = {}
    spec['vasp']['incar'] = incar.to_dict
    spec['vasp']['poscar'] = poscar.to_dict
    spec['vasp']['kpoints'] = kpoints.to_dict
    spec['vasp']['potcar'] = potcar.to_dict
    spec['vaspinputset_name'] = mpvis.__class__.__name__
    spec['task_type'] = 'GGA optimize structure (2x) example'

    # set up the custodian that we want to run
    jobs = VaspJob.double_relaxation_run('', gzipped=False)
    for j in jobs: # turn off auto npar, it doesn't work for >1 node
            j.auto_npar = False
    handlers = [VaspErrorHandler(), FrozenJobErrorHandler(), MeshSymmetryErrorHandler(),
                    NonConvergingErrorHandler()]
    c_params = {'jobs': [j.to_dict for j in jobs], 'handlers': [h.to_dict for h in handlers], 'max_errors': 5}
    custodiantask = VaspCustodianTaskEx(c_params)

    # 1st FireWork - run GGA optimize structure
    # VaspWriterTask - write input files (INCAR, POSCAR, KPOINTS, POSCAR) based on spec
    # CustodianTaskEx - run VASP within a custodian
    tasks = [VaspWriterTask(), custodiantask]
    fws.append(FireWork(tasks, spec, name=get_name(structure, spec['task_type']), fw_id=1))

    # 2nd FireWork - insert previous run into DB
    spec = {'task_type': 'VASP db insertion example'}
    fws.append(
        FireWork([VaspToDBTaskEx()], spec, name=get_name(structure, spec['task_type']), fw_id=2))
    connections[1] = [2]

    # 3rd FireWork - static run.
    # VaspCopyTask - copy output from previous run to this directory
    # SetupStaticRunTask - override old parameters for static run
    # CustodianTaskEx - run VASP within a custodian
    spec = {'task_type': 'GGA static example'}
    copytask = VaspCopyTask({'use_CONTCAR': True, 'skip_CHGCAR': True})
    setuptask = SetupStaticRunTask()
    custodiantask = VaspCustodianTaskEx({'jobs': [VaspJob('', auto_npar=False).to_dict], 'handlers': [h.to_dict for h in handlers], 'max_errors': 5})
    fws.append(FireWork([copytask, setuptask, custodiantask], spec, name=get_name(structure, spec['task_type']), fw_id=3))
    connections[2] = [3]

    # 4th FireWork - insert previous run into DB
    spec = {'task_type': 'VASP db insertion example'}
    fws.append(
        FireWork([VaspToDBTaskEx()], spec, name=get_name(structure, spec['task_type']), fw_id=4))
    connections[3] = [4]

    return Workflow(fws, connections, name=get_slug(structure.formula))

if __name__ == '__main__':
    l = Lattice.from_parameters(3.866, 3.866, 3.866, 60, 60, 60)
    s = Structure(l, ['Si', 'Si'], [[0.125,0.125,0.125], [0.875,0.875,0.875]])

    my_wf = structure_to_wf(s)
    pprint(my_wf.to_dict(), indent=2)
    my_wf.to_file("Si_wf.json")
