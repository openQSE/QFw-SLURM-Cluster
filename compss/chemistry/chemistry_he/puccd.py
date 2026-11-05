from pyscf import gto, scf, ao2mo, fci 
from pyscf.tools import fcidump
import numpy as np  
import openfermion as of 
# from openfermion import *
#from openfermion import ops
import scipy
import copy as cp

from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit.quantum_info import SparsePauliOp

from qiskit_aer import AerSimulator
from qiskit.primitives import BackendEstimatorV2
from qiskit.primitives import StatevectorEstimator
np.random.seed(10)

estimator = None

def puccd_initialize(qfw=False, provider=None, shots=None):
	global estimator

	if qfw:
		from qfw_qiskit import QFwBackend, QFwEstimatorV2
		qfwbackend = QFwBackend(provider=provider or "nwqsim")
		if shots:
			qfwbackend.options.shots = shots
		estimator = QFwEstimatorV2(backend=qfwbackend)
		print(f"Estimator initialized with {qfwbackend}")
		return

	estimator = StatevectorEstimator()

def puccd_finalize(qfw=False):
	global estimator

	if qfw:
		estimator.shutdown()
		print("estimator cleaned up")

comment = """
mol = gto.Mole()
mol.atom = [('He', (0,0,0)),('He', (0,0,2))]
# mol.atom=[('He',(0,0,0))]
# mol.atom=[('H', (0,0,0)),('H', (0,0,1)),('H', (0,0,2)),('H', (0,0,3)),]
mol.max_memory = 8e3 # MB
mol.charge = 0
mol.spin = 0
mol.unit = 'B'
#mol.basis = "STO-3G"
mol.basis = "cc-pvdz"
mol.symmetry = False
mol.build()

n_orb = mol.nao_nr()
n_a, n_b = mol.nelec  
n_elec = n_a+n_b
e_nuc = mol.get_enuc()

mf = scf.RHF(mol)
mf.conv_tol_grad = 1e-14
mf.max_cycle = 200
mf.kernel()

cisolver = fci.FCI(mf)
e,fcivec = cisolver.kernel()
print('E(FCI) = %.12f' % e)


h1ao = scf.hf.get_hcore(mol)
h1mo = np.dot(mf.mo_coeff.T,np.dot(h1ao,mf.mo_coeff))

# h2mo = ao2mo.full(mol, mf.mo_coeff)
h2ao = mol.intor('int2e_sph')

h2mo = np.einsum("pqrs,pi->iqrs",h2ao,mf.mo_coeff)
h2mo = np.einsum("iqrs,qj->ijrs",h2mo,mf.mo_coeff)
h2mo = np.einsum("ijrs,rk->ijks",h2mo,mf.mo_coeff)
h2mo = np.einsum("ijks,sl->ijkl",h2mo,mf.mo_coeff)

# print(h2mo.shape)
g = np.zeros_like(h1mo)
for p in range(0,n_orb):
	for q in range(0,n_orb):
		g[p,q] += h1mo[p,q]
		for r in range(0,n_orb):
			g[p,q] -= 0.5 * h2mo[p,r,r,q]
"""
def pauli_term(paulis,coeff,n_qubits):
	pauli_word = ['I' for i in range(n_qubits)]
	# print(pauli_word)
	for pauli in paulis:
		# print(pauli)
		# print(pauli[0])
		# print(pauli[1])
		if(pauli_word[pauli[0]]=='I'):
			pauli_word[pauli[0]] = pauli[1]
		elif(pauli_word[pauli[0]]=='Z'):
			if(pauli[1]=='Z'):
				pauli_word[pauli[0]] = 'I'
			elif(pauli[1]=='Y'):
				pauli_word[pauli[0]] = 'X'
				coeff = coeff*-1.0j
			elif(pauli[1]=="X"):
				pauli_word[pauli[0]] = 'Y'
				coeff = coeff*1.0j
		elif(pauli_word[pauli[0]]=='Y'):
			if(pauli[1]=='Z'):
				pauli_word[pauli[0]] = 'X'
				coeff = coeff*1.0j
			elif(pauli[1]=='Y'):
				pauli_word[pauli[0]] = 'I'
			elif(pauli[1]=='X'):
				pauli_word[pauli[0]] = 'Z'
				coeff = coeff*-1.0j
		elif(pauli_word[pauli[0]]=='X'):
			if(pauli[1]=='Z'):
				pauli_word[pauli[0]] = 'Y'
				coeff = coeff*-1.0j
			if(pauli[1]=='Y'):
				pauli_word[pauli[0]] = 'Z'
				coeff = coeff*1.0j
			if(pauli[1]=='X'):
				pauli_word[pauli[0]] = 'I'
	return(pauli_word,coeff)

def of2qristal(qubit_op,n_qubits):
	pauli_words = dict()
	terms = qubit_op.terms
	for term in terms:
		pauli_word = ['I' for i in range(n_qubits)]
		for pauli in term:
			pauli_word[pauli[0]] = pauli[1]
		pauli_words[tuple(pauli_word)] = terms.get(term)
	return pauli_words

def of2qiskit(qubit_op,n_qubits):
	terms=qubit_op.terms 
	# observables = []
	# words = []
	# coeffs = []
	weights = {}

	for term, coeff in terms.items():
		label = list('I'*n_qubits)
		for index, pauli in term:
			label[index] = pauli 
		#word = "".join(label)
		word = "".join(reversed(label))
		#word = "".join(reversed(word))
		# words.append(word)
		# coeffs.append(coeff)
		# observables.append([SparsePauliOp(word)])
		weights[word] = coeff 

	return weights


class pairUCC:
#{
	def __init__(self,n_elec_pairs:int, h1mo:np.ndarray, h2mo:np.ndarray, enuc:float, frozen_orbs=False):
		# electrons and orbitals
		self.n_elec_pairs = n_elec_pairs
		self.h1mo = h1mo
		self.h2mo = h2mo
		self.enuc = enuc
		self.n_orb = len(self.h1mo)
		self.C = np.eye(self.n_orb)
		self.gmo = cp.deepcopy(self.h1mo)
		for i in range(0,self.n_orb):
			for j in range(0,self.n_orb):
				for k in range(0,self.n_orb):
					self.gmo[i,j] -= 0.5*self.h2mo[i,k,k,j]     
		self.curr_e = 0.0

		# frozen orbital implementation
		active_mask = np.ones(self.n_orb,dtype=bool)
		if frozen_orbs is None:
			self.active_mask = active_mask
		elif isinstance(frozen_orbs, (int, np.integer)):
			active_mask[:frozen_orbs] = False
			self.active_mask = active_mask
		elif isinstance(frozen_orbs, tuple):
			active_mask[:frozen_orbs[0]] = False
			active_mask[-frozen_orbs[1]:] = False
			self.active_mask = active_mask
		elif isinstance(frozen_orbs, (list, np.array)):
			active_mask[list(frozen_orbs)] = False
			self.active_mask = active_mask
		else:
			print("ERROR: Please provide frozen orbitals as None, int, tuple, or list!")
			exit()

		# vqe elements
		self.n_qubits = np.sum(self.active_mask)
		act_occ = np.sum(self.active_mask[:self.n_elec_pairs])
		act_virt = np.sum(self.active_mask[self.n_elec_pairs:])
		self.n_vqe_params = act_occ * act_virt
		self.vqe_params = np.zeros(self.n_vqe_params)
		self.ref = of.linalg.jw_configuration_state(list(range(0,act_occ)),self.n_qubits)
		ops = []
		for i in reversed(range(0, self.n_elec_pairs)):
			if(self.active_mask[i]):
				i_idx = int(np.sum(self.active_mask[:i]))
				for a in range(self.n_elec_pairs,self.n_orb):
					if(self.active_mask[a]):
						a_idx = int(np.sum(self.active_mask[:a]))
						ex_op =  of.QubitOperator(((a_idx,'X'),(i_idx,'Y')),  0.5j)
						ex_op += of.QubitOperator(((i_idx,'X'),(a_idx,'Y')), -0.5j)		
						ex_mat = of.linalg.get_sparse_operator(ex_op, n_qubits=self.n_qubits)		
						ops.append(ex_mat)
		self.ops = ops
		print("Initialized pUCCD object using 1- and 2-electron integrals for",
		   	self.n_elec_pairs, "electron pair(s) in", self.n_orb, "MOs!")
		print("Nuclear repulsion: ", self.enuc)
		return

	@classmethod
	def from_pyscf_Mole(cls, molecule:gto.Mole):
		"""
		Initializes a pUCCD ansatz from a pyscf Mole object
		"""
		print("Setting up pUCCD object from pyscf.gto.M object...")
		n_orb = molecule.nao_nr()
		n_elec_pairs = molecule.nelec[0]  
		enuc = molecule.get_enuc()

		mf = scf.RHF(molecule)
		mf.conv_tol_grad = 1e-14
		mf.max_cycle = 200
		mf.kernel()

		h1ao = scf.hf.get_hcore(molecule)
		h1mo = np.dot(mf.mo_coeff.T,np.dot(h1ao,mf.mo_coeff))

		h2ao = molecule.intor('int2e_sph')
		h2mo = np.einsum("pqrs,pi->iqrs",h2ao,mf.mo_coeff)
		h2mo = np.einsum("iqrs,qj->ijrs",h2mo,mf.mo_coeff)
		h2mo = np.einsum("ijrs,rk->ijks",h2mo,mf.mo_coeff)
		h2mo = np.einsum("ijks,sl->ijkl",h2mo,mf.mo_coeff)

		print("Done!")
		return cls(n_elec_pairs, h1mo, h2mo, enuc)

	@classmethod
	def from_FCIDUMP(cls, fcidump_file:str):
		"""
		Initializes a pUCCD ansatz from a FCIDUMP file
		"""
		print("Setting up pUCCD object from FCIDUMP file...")
		print("Reading data from", fcidump_file)
		fcidump_data = fcidump.read(fcidump_file)
		print("Success!")
		n_elec_pairs = fcidump_data['NELEC']//2
		# restore 2e integral symmetry
		h2mo = ao2mo.addons.restore(1, fcidump_data['H2'], fcidump_data['NORB'])
		return cls(n_elec_pairs, fcidump_data['H1'], h2mo, fcidump_data['ECORE'])

	def freeze_orbs(self, frozen_orbs=None):
		"""
		Freezes a subset of the molecular orbitals to save computational cost
		Frozen occupied orbitals have fixed occupation number of 1
		Frozen virtual orbitals have fixed occupation number of 0
		"""
		active_mask = np.ones(self.n_orb,dtype=bool)
		if frozen_orbs is None:
			self.active_mask = active_mask
		elif isinstance(frozen_orbs, (int, np.integer)):
			active_mask[:frozen_orbs] = False
			self.active_mask = active_mask
		elif isinstance(frozen_orbs, tuple):
			active_mask[:frozen_orbs[0]] = False
			active_mask[-frozen_orbs[1]:] = False
			self.active_mask = active_mask
		elif isinstance(frozen_orbs, (list, np.array)):
			active_mask[list(frozen_orbs)] = False
			self.active_mask = active_mask
		else:
			print("ERROR: Please provide frozen orbitals as None, int, tuple, or list!")
			exit()

		# vqe elements
		self.n_qubits = np.sum(self.active_mask)
		act_occ = np.sum(self.active_mask[:self.n_elec_pairs])
		act_virt = np.sum(self.active_mask[self.n_elec_pairs:])
		self.n_vqe_params = act_occ * act_virt
		self.vqe_params = np.zeros(self.n_vqe_params)
		self.ref = of.linalg.jw_configuration_state(list(range(0,act_occ)),self.n_qubits)
		ops = []
		for i in reversed(range(0, self.n_elec_pairs)):
			if(self.active_mask[i]):
				i_idx = int(np.sum(self.active_mask[:i]))
				for a in range(self.n_elec_pairs,self.n_orb):
					if(self.active_mask[a]):
						a_idx = int(np.sum(self.active_mask[:a]))
						ex_op =  of.QubitOperator(((a_idx,'X'),(i_idx,'Y')),  0.5j)
						ex_op += of.QubitOperator(((i_idx,'X'),(a_idx,'Y')), -0.5j)		
						ex_mat = of.linalg.get_sparse_operator(ex_op, n_qubits=self.n_qubits)		
						ops.append(ex_mat)
		self.ops = ops
		print("Initialized pUCCD object using 1- and 2-electron integrals for",
		   	self.n_elec_pairs, "electron pair(s) in", self.n_orb, "MOs!")
		print("Nuclear repulsion: ", self.enuc)
		return

	def rdm1(self, p:int, coeff: float): 
		"""
		Helper function for generating qubit Hamiltonian, gradient, and hessian
		"""
		pauli_op = of.QubitOperator("", 0.0)
		if(self.active_mask[p]):
			p_idx = int(np.sum(self.active_mask[:p]))
			pauli_op += of.QubitOperator("", coeff)
			pauli_op += of.QubitOperator(((p_idx,'Z')), -coeff)
			return pauli_op
		elif(p < self.n_elec_pairs):
			pauli_op += of.QubitOperator("", 2*coeff)
			return pauli_op
		else:
			return pauli_op

	def rdm2a(self, p:int, q:int, coeff:float):
		"""
		Helper function for generating qubit Hamiltonian, gradient, and hessian
		"""
		pauli_op = of.QubitOperator("", 0.0)
		if(self.active_mask[p]):
			p_idx = int(np.sum(self.active_mask[:p]))
			if(self.active_mask[q]):
				q_idx = int(np.sum(self.active_mask[:q]))
				pauli_op += of.QubitOperator("", 0.5*coeff)
				pauli_op += of.QubitOperator(((p_idx,'Z')), -0.5*coeff)
				pauli_op += of.QubitOperator(((q_idx,'Z')), -0.5*coeff)
				pauli_op += of.QubitOperator(((p_idx,'Z'),(q_idx,'Z')),  0.5*coeff)
				return pauli_op
			elif(q < self.n_elec_pairs):
				pauli_op += of.QubitOperator("", coeff)
				pauli_op += of.QubitOperator(((p_idx,'Z')), -coeff)
				return pauli_op
			else:
				return pauli_op
		elif(p < self.n_elec_pairs):
			if(self.active_mask[q]):
				q_idx = int(np.sum(self.active_mask[:q]))
				pauli_op += of.QubitOperator("", coeff)
				pauli_op += of.QubitOperator(((q_idx,'Z')), -coeff)
				return pauli_op
			elif(q < self.n_elec_pairs):
				pauli_op += of.QubitOperator("", 2*coeff)
				return pauli_op
			else:
				return pauli_op
		else:
			return pauli_op 

	def rdm2b(self, p:int, q:int, coeff:float):
		"""
		Helper function for generating qubit Hamiltonian, gradient, and hessian
		"""
		pauli_op = of.QubitOperator("", 0.0)
		if(self.active_mask[p]):
			p_idx = int(np.sum(self.active_mask[:p]))
			if(self.active_mask[q]):
				q_idx = int(np.sum(self.active_mask[:q]))
				pauli_op += of.QubitOperator("", 0.25*coeff)
				pauli_op += of.QubitOperator(((p_idx,'Z')), -0.25*coeff)
				pauli_op += of.QubitOperator(((q_idx,'Z')),  0.25*coeff)
				pauli_op += of.QubitOperator(((p_idx,'Z'),(q_idx,'Z')), -0.25*coeff)
				return pauli_op
			elif(q < self.n_elec_pairs):
				return pauli_op
			else:
				pauli_op += of.QubitOperator("", 0.5*coeff)
				pauli_op += of.QubitOperator(((p_idx,'Z')), -0.5*coeff)
				return pauli_op
		elif(p < self.n_elec_pairs):
			if(self.active_mask[q]):
				q_idx = int(np.sum(self.active_mask[:q]))
				pauli_op += of.QubitOperator("", 0.5*coeff)
				pauli_op += of.QubitOperator(((q_idx,'Z')), 0.5*coeff)
				return pauli_op
			elif(q < self.n_elec_pairs):
				return pauli_op	
			else:
				pauli_op += of.QubitOperator("", coeff)
				return pauli_op
		else:
			return pauli_op

	def rdm2c(self, p:int, q:int, coeff:float):
		"""
		Helper function for generating qubit Hamiltonian, gradient, and hessian
		"""
		pauli_op = of.QubitOperator("", 0.0)
		if(self.active_mask[p]):
			p_idx = int(np.sum(self.active_mask[:p]))
			if(self.active_mask[q]):
				q_idx = int(np.sum(self.active_mask[:q]))
				pauli_op += of.QubitOperator(((p_idx,'X'),(q_idx,'X')), 0.5*coeff)
				pauli_op += of.QubitOperator(((p_idx,'Y'),(q_idx,'Y')), 0.5*coeff)
				return pauli_op
			else:
				return pauli_op
		else:
			return pauli_op

	def rotate_orbitals(self,U:np.ndarray):
		"""
		rotate orbitals for orbital optimization procedure
		"""
		assert(U.shape[0] == self.C.shape[1])
		self.h1mo = np.einsum("pq,pi->iq",self.h1mo,U)
		self.h1mo = np.einsum("iq,qj->ij",self.h1mo,U)

		self.h2mo = np.einsum("pqrs,pi->iqrs",self.h2mo,U)
		self.h2mo = np.einsum("iqrs,qj->ijrs",self.h2mo,U)
		self.h2mo = np.einsum("ijrs,rk->ijks",self.h2mo,U)
		self.h2mo = np.einsum("ijks,sl->ijkl",self.h2mo,U)

		self.gmo = cp.deepcopy(self.h1mo)
		for p in range(0,self.n_orb):
			for q in range(0,self.n_orb):
				for r in range(0,self.n_orb):
					self.gmo[p,q] -= 0.5*self.h2mo[p,r,r,q]

		self.C = self.C.dot(U)

	def givens_rot_ansatz(self):
		"""
		Returns a qiskit QuantumCircuit object that implements the pUCCD ansatz of Givens rotations
		"""
		act_occ = int(np.sum(self.active_mask[:self.n_elec_pairs]))
		act_virt = int(np.sum(self.active_mask[self.n_elec_pairs:]))
		tia = ParameterVector('t',length=act_occ*act_virt)
		# initialize ansatz to HF state
		ansatz = QuantumCircuit(self.n_qubits)
		for i in range(0,act_occ):
				ansatz.x(i)
		# implement Givens rotation circuit
		for i in reversed(range(0,act_occ)):
			for a in range(act_occ,self.n_qubits):
				ansatz.barrier()
				ansatz.s(i)
				ansatz.s(a)
				ansatz.h(i)
				ansatz.cx(i,a)
				ansatz.ry(tia[(act_occ-i-1)*act_virt+a-act_occ],i)
				ansatz.ry(tia[(act_occ-i-1)*act_virt+a-act_occ],a)
				ansatz.cx(i,a)
				ansatz.h(i)
				ansatz.sdg(i)
				ansatz.sdg(a)
		return ansatz 

	def observables(self):
		"""
		Creates a list of qiskit observables to be measured by the quantum device
		"""
		obs = []
		#constants
		label = list('I'*self.n_qubits)
		word = "".join(label)
		obs.append(SparsePauliOp(word))
		# Z terms
		for i in range(0,self.n_qubits):
			label = list('I'*self.n_qubits)
			label[i] = 'Z'
			word = "".join(label)
			obs.append(SparsePauliOp(word))
		# ZZ terms
		for i in range(0,self.n_qubits):
			for j in range(i+1,self.n_qubits):
				label=list('I'*self.n_qubits)
				label[i] = 'Z'
				label[j] = 'Z'
				word = "".join(label)
				obs.append(SparsePauliOp(word))
		# XX terms
		for i in range(0,self.n_qubits):
			for j in range(i+1,self.n_qubits):
				label=list('I'*self.n_qubits)
				label[i] = 'X'
				label[j] = 'X'
				word = "".join(label)
				obs.append(SparsePauliOp(word))
		# YY terms
		for i in range(0,self.n_qubits):
			for j in range(i+1,self.n_qubits):
				label=list('I'*self.n_qubits)
				label[i] = 'Y'
				label[j] = 'Y'
				word = "".join(label)
				obs.append(SparsePauliOp(word))
		return obs

	def commuting_observables(self):
		"""
		returns three lists of observables corresponding to those that are 
		simultaneously measureable
		"""
		zbasis = []
		xbasis = []
		ybasis = []
		#constants
		label = list('I'*self.n_qubits)
		word = "".join(label)
		zbasis.append(SparsePauliOp(word))
		for i in range(0,self.n_qubits):
			# Z terms
			label = list('I'*self.n_qubits)
			label[i] = 'Z'
			word = "".join(label)
			zbasis.append(SparsePauliOp(word))
			for j in range(i+1,self.n_qubits):
				# ZZ terms
				label=list('I'*self.n_qubits)
				label[i] = 'Z'
				label[j] = 'Z'
				word = "".join(label)
				zbasis.append(SparsePauliOp(word))
				# XX terms
				label=list('I'*self.n_qubits)
				label[i] = 'X'
				label[j] = 'X'
				word = "".join(label)
				xbasis.append(SparsePauliOp(word))
				# YY terms
				label=list('I'*self.n_qubits)
				label[i] = 'Y'
				label[j] = 'Y'
				word = "".join(label)
				ybasis.append(SparsePauliOp(word))
		return zbasis, xbasis, ybasis

	def energy_of_determinant(self,config_a:list,config_b:list):
		"""
		returns the energy of a determinant specified
		by lists of occupied orbitals
		"""
		e1 = 0
		e2 = 0
		for i in config_a:
			e1 += self.h1mo[i,i]
		for i in config_b:
			e1 += self.h1mo[i,i]
		for i in config_a:
			for j in config_a:
				if i>=j:
					continue
				e2 += self.h2mo[i,i,j,j]
				e2 -= self.h2mo[i,j,j,i]
		for i in config_b:
			for j in config_b:
				if i>=j:
					continue
				e2 += self.h2mo[i,i,j,j]
				e2 -= self.h2mo[i,j,j,i]
		for i in config_a:
			for j in config_b:
				e2 += self.h2mo[i,i,j,j]
		print("One-body = %16.10f"%e1)
		print("Two-body = %16.10f"%e2)
		e_det = e1 + e2 + self.e_nuc 
		print("Determinant energy = %16.10f"%e_det)
		return e_det

	def ham_qubit(self):
		"""
		Returns an openfermion QubitOperator of the pair-encoded Hamiltonian
		"""
		ham_op = of.QubitOperator("",self.enuc)
		for p in range(0,self.n_orb):
			ham_op += self.rdm1(p, self.gmo[p,p])
			for q in range(0, self.n_orb):
				ham_op += self.rdm2a(p,q,self.h2mo[p,p,q,q])
				if(p!=q):
					ham_op += self.rdm2b(p,q,self.h2mo[p,q,q,p])
					if(p>q):
						ham_op += self.rdm2c(p,q,self.h2mo[p,q,p,q])
		return ham_op

	def orb_grad_qubit2(self, p:int, q:int):
		"""
		Returns an OpenFermion QubitOperator of the pqth element of the orbital gradient
		"""
		grad_op = of.QubitOperator("", 0.0)
		grad_op += self.rdm1(q,  self.gmo[p,q]+self.gmo[q,p])
		grad_op += self.rdm1(p, -self.gmo[p,q]-self.gmo[q,p])
		for t in range(0, self.n_orb):
			grad_op += self.rdm2a(q, t,  2*(self.h2mo[q,p,t,t]+self.h2mo[p,q,t,t]))
			grad_op += self.rdm2a(p, t, -2*(self.h2mo[q,p,t,t]+self.h2mo[p,q,t,t]))
			if(t != q):
				grad_op += self.rdm2b(q, t,  self.h2mo[q,t,t,p]+self.h2mo[p,t,t,q])
				grad_op += self.rdm2b(t, q,  self.h2mo[q,t,t,p]+self.h2mo[p,t,t,q])
			if(t != p):
				grad_op += self.rdm2b(p, t, -self.h2mo[q,t,t,p]-self.h2mo[p,t,t,q])
				grad_op += self.rdm2b(t, p, -self.h2mo[q,t,t,p]-self.h2mo[p,t,t,q])
			if(t > q):
				grad_op += self.rdm2c(t, q,  2*self.h2mo[t,q,t,p])
			if(t < q):
				grad_op += self.rdm2c(q, t,  2*self.h2mo[p,t,q,t])
			if(t < p):
				grad_op += self.rdm2c(p, t, -2*self.h2mo[q,t,p,t])
			if(t > p):
				grad_op += self.rdm2c(t, p, -2*self.h2mo[t,p,t,q])
		return grad_op

	def orb_hess_qubit2(self, p:int, q:int, r:int, s:int):
		"""
		Returns an OpenFermion QubitOperator of the pq,rs element of the orbital hessian
		"""
		hess_op = of.QubitOperator("", 0.0)
		if(p==r):
			hess_op += self.rdm1(p,  0.5*(self.gmo[q,s]+self.gmo[s,q]))
			hess_op += self.rdm1(q, -0.5*(self.gmo[q,s]+self.gmo[s,q]))
			hess_op += self.rdm1(r,  0.5*(self.gmo[q,s]+self.gmo[s,q]))
			hess_op += self.rdm1(s, -0.5*(self.gmo[q,s]+self.gmo[s,q]))
		if(p==s):
			hess_op += self.rdm1(p, -0.5*(self.gmo[q,r]+self.gmo[r,q]))
			hess_op += self.rdm1(q,  0.5*(self.gmo[q,r]+self.gmo[r,q]))
			hess_op += self.rdm1(r,  0.5*(self.gmo[q,r]+self.gmo[r,q]))
			hess_op += self.rdm1(s, -0.5*(self.gmo[q,r]+self.gmo[r,q]))
		if(q==r):
			hess_op += self.rdm1(p,  0.5*(self.gmo[p,s]+self.gmo[s,p]))
			hess_op += self.rdm1(q, -0.5*(self.gmo[p,s]+self.gmo[s,p]))
			hess_op += self.rdm1(r, -0.5*(self.gmo[p,s]+self.gmo[s,p]))
			hess_op += self.rdm1(s,  0.5*(self.gmo[p,s]+self.gmo[s,p]))
		if(q==s):
			hess_op += self.rdm1(p, -0.5*(self.gmo[p,r]+self.gmo[r,p]))
			hess_op += self.rdm1(q,  0.5*(self.gmo[p,r]+self.gmo[r,p]))
			hess_op += self.rdm1(r, -0.5*(self.gmo[p,r]+self.gmo[r,p]))
			hess_op += self.rdm1(s,  0.5*(self.gmo[p,r]+self.gmo[r,p]))
		
		hess_op += self.rdm2a(p, r,  2*(self.h2mo[p,q,r,s]+self.h2mo[p,q,s,r]+self.h2mo[q,p,r,s]+self.h2mo[q,p,s,r]))
		hess_op += self.rdm2a(p, s, -2*(self.h2mo[p,q,r,s]+self.h2mo[p,q,s,r]+self.h2mo[q,p,r,s]+self.h2mo[q,p,s,r]))
		hess_op += self.rdm2a(q, r, -2*(self.h2mo[p,q,r,s]+self.h2mo[p,q,s,r]+self.h2mo[q,p,r,s]+self.h2mo[q,p,s,r]))
		hess_op += self.rdm2a(q, s,  2*(self.h2mo[p,q,r,s]+self.h2mo[p,q,s,r]+self.h2mo[q,p,r,s]+self.h2mo[q,p,s,r]))

		if(p!=r):
			hess_op += self.rdm2b(p, r,  self.h2mo[q,r,s,p]+self.h2mo[p,r,s,q]+self.h2mo[q,s,r,p]+self.h2mo[p,s,r,q])
			hess_op += self.rdm2b(r, p,  self.h2mo[q,r,s,p]+self.h2mo[p,r,s,q]+self.h2mo[q,s,r,p]+self.h2mo[p,s,r,q])
			if(p>r):
				hess_op += self.rdm2c(p, r, 2*(self.h2mo[s,p,r,q]+self.h2mo[s,q,r,p]))
			if(p<r):
				hess_op += self.rdm2c(r, p, 2*(self.h2mo[p,s,q,r]+self.h2mo[q,s,p,r]))
		if(p!=s):
			hess_op += self.rdm2b(p, s, -self.h2mo[q,r,s,p]-self.h2mo[p,r,s,q]-self.h2mo[q,s,r,p]-self.h2mo[p,s,r,q])
			hess_op += self.rdm2b(s, p, -self.h2mo[q,r,s,p]-self.h2mo[p,r,s,q]-self.h2mo[q,s,r,p]-self.h2mo[p,s,r,q])
			if(p>s):
				hess_op += self.rdm2c(p, s, -2*(self.h2mo[q,s,p,r]+self.h2mo[q,r,p,s]))
			if(p<s):
				hess_op += self.rdm2c(s, p, -2*(self.h2mo[s,q,r,p]+self.h2mo[r,q,s,p]))
		if(q!=r):
			hess_op += self.rdm2b(q, r, -self.h2mo[q,r,s,p]-self.h2mo[p,r,s,q]-self.h2mo[q,s,r,p]-self.h2mo[p,s,r,q])
			hess_op += self.rdm2b(r, q, -self.h2mo[q,r,s,p]-self.h2mo[p,r,s,q]-self.h2mo[q,s,r,p]-self.h2mo[p,s,r,q])
			if(q>r):
				hess_op += self.rdm2c(q, r, -2*(self.h2mo[s,q,r,p]+self.h2mo[r,q,s,p]))
			if(q<r):
				hess_op += self.rdm2c(r, q, -2*(self.h2mo[p,r,q,s]+self.h2mo[p,s,q,r]))
		if(q!=s):
			hess_op += self.rdm2b(q, s,  self.h2mo[q,r,s,p]+self.h2mo[p,r,s,q]+self.h2mo[q,s,r,p]+self.h2mo[p,s,r,q])
			hess_op += self.rdm2b(s, q,  self.h2mo[q,r,s,p]+self.h2mo[p,r,s,q]+self.h2mo[q,s,r,p]+self.h2mo[p,s,r,q])
			if(q>s):
				hess_op += self.rdm2c(q, s, 2*(self.h2mo[r,q,s,p]+self.h2mo[s,q,r,p]))
			if(q<s):
				hess_op += self.rdm2c(s, q, 2*(self.h2mo[p,s,q,r]+self.h2mo[p,r,q,s]))

		for t in range(0, self.n_orb):
			if(p==r):
				hess_op += self.rdm2a(p, t,  self.h2mo[s,q,t,t]+self.h2mo[q,s,t,t])
				hess_op += self.rdm2a(q, t, -self.h2mo[s,q,t,t]-self.h2mo[q,s,t,t])
				hess_op += self.rdm2a(r, t,  self.h2mo[s,q,t,t]+self.h2mo[q,s,t,t])
				hess_op += self.rdm2a(s, t, -self.h2mo[s,q,t,t]-self.h2mo[q,s,t,t])
				if(p!=t):
					hess_op += self.rdm2b(p, t,  0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					hess_op += self.rdm2b(t, p,  0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					if(p>t):
						hess_op += self.rdm2c(p, t, self.h2mo[t,q,t,s])
					if(p<t):
						hess_op += self.rdm2c(t, p, self.h2mo[q,t,s,t])
				if(q!=t):
					hess_op += self.rdm2b(q, t, -0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					hess_op += self.rdm2b(t, q, -0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					if(q>t):
						hess_op += self.rdm2c(q, t, -self.h2mo[t,q,t,s])
					if(q<t):
						hess_op += self.rdm2c(t, q, -self.h2mo[q,t,s,t])
				if(r!=t):
					hess_op += self.rdm2b(r, t,  0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					hess_op += self.rdm2b(t, r,  0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					if(r>t):
						hess_op += self.rdm2c(r, t,  self.h2mo[t,q,t,s])
					if(r<t):
						hess_op += self.rdm2c(t, r,  self.h2mo[q,t,s,t])
				if(s!=t):
					hess_op += self.rdm2b(s, t, -0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					hess_op += self.rdm2b(t, s, -0.5*(self.h2mo[q,t,t,s]+self.h2mo[t,q,s,t]))
					if(s>t):
						hess_op += self.rdm2c(s, t, -self.h2mo[t,q,t,s])
					if(s<t):
						hess_op += self.rdm2c(t, s, -self.h2mo[q,t,s,t])
			if(p==s):
				hess_op += self.rdm2a(p, t, -self.h2mo[q,r,t,t]-self.h2mo[r,q,t,t])
				hess_op += self.rdm2a(q, t,  self.h2mo[q,r,t,t]+self.h2mo[r,q,t,t])
				hess_op += self.rdm2a(r, t,  self.h2mo[q,r,t,t]+self.h2mo[r,q,t,t])
				hess_op += self.rdm2a(s, t, -self.h2mo[q,r,t,t]-self.h2mo[r,q,t,t])
				if(p!=t):
					hess_op += self.rdm2b(p, t, -0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					hess_op += self.rdm2b(t, p, -0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					if(p>t):
						hess_op += self.rdm2c(p, t, -self.h2mo[t,q,t,r])
					if(p<t):
						hess_op += self.rdm2c(t, p, -self.h2mo[q,t,r,t])
				if(q!=t):
					hess_op += self.rdm2b(q, t,  0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					hess_op += self.rdm2b(t, q,  0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					if(q>t):
						hess_op += self.rdm2c(q, t,  self.h2mo[t,q,t,r])
					if(q<t):
						hess_op += self.rdm2c(t, q,  self.h2mo[q,t,r,t])
				if(r!=t):
					hess_op += self.rdm2b(r, t,  0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					hess_op += self.rdm2b(t, r,  0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					if(r>t):
						hess_op += self.rdm2c(r, t, self.h2mo[t,q,t,r])
					if(r<t):
						hess_op += self.rdm2c(t, r, self.h2mo[q,t,r,t])
				if(s!=t):
					hess_op += self.rdm2b(s, t, -0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					hess_op += self.rdm2b(t, s, -0.5*(self.h2mo[q,t,t,r]+self.h2mo[t,q,r,t]))
					if(s>t):
						hess_op += self.rdm2c(s, t, -self.h2mo[t,r,t,q])
					if(s<t):
						hess_op += self.rdm2c(t, s, -self.h2mo[r,t,q,t])
			if(q==r):
				hess_op += self.rdm2a(p, t,  self.h2mo[p,s,t,t]+self.h2mo[s,p,t,t])
				hess_op += self.rdm2a(q, t, -self.h2mo[p,s,t,t]-self.h2mo[s,p,t,t])
				hess_op += self.rdm2a(r, t, -self.h2mo[p,s,t,t]-self.h2mo[s,p,t,t])
				hess_op += self.rdm2a(s, t,  self.h2mo[p,s,t,t]+self.h2mo[s,p,t,t])
				if(p!=t):
					hess_op += self.rdm2b(p, t,  0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					hess_op += self.rdm2b(t, p,  0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					if(p>t):
						hess_op += self.rdm2c(p, t, self.h2mo[t,p,t,s])
					if(p<t):
						hess_op += self.rdm2c(t, p, self.h2mo[p,t,s,t])
				if(q!=t):
					hess_op += self.rdm2b(q, t, -0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					hess_op += self.rdm2b(t, q, -0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					if(q>t):
						hess_op += self.rdm2c(q, t, -self.h2mo[t,p,t,s])
					if(q<t):
						hess_op += self.rdm2c(t, q, -self.h2mo[p,t,s,t])
				if(r!=t):
					hess_op += self.rdm2b(r, t, -0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					hess_op += self.rdm2b(t, r, -0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					if(r>t):
						hess_op += self.rdm2c(r, t, -self.h2mo[t,p,t,s])
					if(r<t):
						hess_op += self.rdm2c(t, r, -self.h2mo[p,t,s,t])
				if(s!=t):
					hess_op += self.rdm2b(s, t,  0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					hess_op += self.rdm2b(t, s,  0.5*(self.h2mo[p,t,t,s]+self.h2mo[t,p,s,t]))
					if(s>t):
						hess_op += self.rdm2c(s, t,  self.h2mo[t,p,t,s])
					if(s<t):
						hess_op += self.rdm2c(t, s,  self.h2mo[p,t,s,t])
			if(q==s):
				hess_op += self.rdm2a(p, t, -self.h2mo[p,r,t,t]-self.h2mo[r,p,t,t])
				hess_op += self.rdm2a(q, t,  self.h2mo[p,r,t,t]+self.h2mo[r,p,t,t])
				hess_op += self.rdm2a(r, t, -self.h2mo[p,r,t,t]-self.h2mo[r,p,t,t])
				hess_op += self.rdm2a(s, t,  self.h2mo[p,r,t,t]+self.h2mo[r,p,t,t])
				if(p!=t):
					hess_op += self.rdm2b(p, t, -0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					hess_op += self.rdm2b(t, p, -0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					if(p>t):
						hess_op += self.rdm2c(p, t, -self.h2mo[t,p,t,r])
					if(p<t):
						hess_op += self.rdm2c(t, p, -self.h2mo[p,t,r,t])
				if(q!=t):
					hess_op += self.rdm2b(q, t,  0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					hess_op += self.rdm2b(t, q,  0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					if(q>t):
						hess_op += self.rdm2c(q, t,  self.h2mo[t,p,t,r])
					if(q<t):
						hess_op += self.rdm2c(t, q,  self.h2mo[p,t,r,t])
				if(r!=t):
					hess_op += self.rdm2b(r, t, -0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					hess_op += self.rdm2b(t, r, -0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					if(r>t):
						hess_op += self.rdm2c(r, t, -self.h2mo[t,p,t,r])
					if(r<t):
						hess_op += self.rdm2c(t, r, -self.h2mo[p,t,r,t])
				if(s!=t):
					hess_op += self.rdm2b(s, t,  0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					hess_op += self.rdm2b(t, s,  0.5*(self.h2mo[p,t,t,r]+self.h2mo[t,p,r,t]))
					if(s>t):
						hess_op += self.rdm2c(s, t,  self.h2mo[t,p,t,r])
					if(s<t):
						hess_op += self.rdm2c(t, s,  self.h2mo[p,t,r,t])
		return hess_op

	def prepare_state(self,params:list):
		"""
		Returns the vector corresponding to the current trial state
		"""
		new_state = self.ref * 1.0
		for i in range(0,len(params)):
			new_state = scipy.sparse.linalg.expm_multiply((params[i]*self.ops[i]),new_state)
		return new_state

	def initial_guess_mp2d(self):
		"""
		Returns an array of parameters corresponding to the diagonal MP2 approximation as an
		initial guess for the ansatz parameters
		"""
		# build the fock diagonal
		fdmo = np.zeros(self.n_orb)
		for p in range(0,self.n_orb):
			fdmo[p] += self.h1mo[p,p]
			for q in range(0,self.n_elec_pairs):
				fdmo[p] += 2*self.h2mo[p,p,q,q]-self.h2mo[p,q,q,p]
		# initialize guess vector
		guess = []
		for i in reversed(range(0,self.n_elec_pairs)):
			if(self.active_mask[i]):
				i_idx = int(np.sum(self.active_mask[:i]))
				for a in range(self.n_elec_pairs,self.n_orb):
					if(self.active_mask[a]):
						a_idx = int(np.sum(self.active_mask[:a]))
						tia = self.h2mo[i,a,i,a] / (2*fdmo[i]-2*fdmo[a])
						guess.append(tia)
		return np.array(guess)
		
	def energy(self,params:list):
		"""
		Computes the energy using the supplied ansatz parameters and the member Hamiltonian
		"""
		state = self.prepare_state(params)
		ham = of.linalg.get_sparse_operator(self.ham_qubit(),n_qubits=self.n_qubits)
		e = state.transpose().conj().dot(ham.dot(state))
		assert(np.isclose(e.imag,0))
		return e.real 

	def measure_expectations_qk(self,params:list):
		"""
		measure the expectation value of observables with a qiskit ansatz 
		and return a dictionary of expectation values and standard deviations
		"""
		global estimator

		if not estimator:
			raise ValueError("PUCCD module not initialized")

		circuit = self.givens_rot_ansatz()
		observables = self.observables()
		parameters = [params]
		job = estimator.run([(circuit, observables, parameters)])
		result = job.result()
		evs = {}
		stds = {}
		for i in range(0,len(observables)):
			evs[str(observables[i].paulis[0])] = result[0].data.evs[i]
			stds[str(observables[i].paulis[0])] = result[0].data.stds[i]
		self.evs = evs 
		self.stds = stds
		return evs, stds

	def compute_energy_qk(self,params:list):
		# generate a list of observables to be measured by the quantum hardware
		evs, stds = self.measure_expectations_qk(params)
		ham = of2qiskit(self.ham_qubit(),self.n_qubits)
		energy = 0.0
		for word, weight in ham.items():
			energy += weight*evs[word]
		return energy

	def expected_energy(self):
		# uses member hamiltonian and expectation values to compute <H>
		ham = of2qiskit(self.ham_qubit(),self.n_qubits)
		energy = 0.0
		for word, weight in ham.items():
			energy += weight*self.evs[word]
		return energy

	def optimize_amps_qk(self, params:list, thresh:float=1e-4, maxiter_amps:int=1000):
		iteration = 0
		def callback(xk):
			nonlocal iteration
			print(f"Iteration {iteration}: Current energy = {self.expected_energy()}")
			iteration +=1 

		print("Optimizer: COBYLA")
		bounds = [(-1.0*np.pi, np.pi)]*self.n_vqe_params
		opt_result = scipy.optimize.minimize(
			self.compute_energy_qk,
			params,
			method='COBYLA',
			tol=thresh,
			bounds=bounds,
			callback=callback,
			options={'maxiter': maxiter_amps}
			)
		print(opt_result['success'])
		print(opt_result['message'])
		new_params = list(opt_result['x'])
		new_e = self.energy(new_params)
		print("Optimized energy = %.15f"%new_e)
		print("Optimized parameters = ", new_params)
		self.vqe_params = new_params
		self.curr_e = new_e
		return new_e

	def optimize_amps(self,params:list, thresh:float=1e-5):
		iteration = 0
		def callback(xk):
			nonlocal iteration
			print(f"Iteration {iteration}: Current energy = {self.energy(xk)}")
			iteration += 1

		print("Optimizer: COBYLA")
		opt_result = scipy.optimize.minimize(self.energy, params, method='COBYLA', tol=thresh, callback=callback, options={'disp': True})
		print(opt_result['success'])
		print(opt_result['message'])
		new_params = list(opt_result['x'])
		new_e = self.energy(new_params)
		print("Optimized energy = %.15f"%new_e)
		print("Optimized parameters = ", new_params)
		self.vqe_params = new_params
		self.curr_e = new_e
		return new_e

	def orb_grad(self,params:list):
		state = self.prepare_state(params)
		grad = []
		for p in range(0,self.n_orb):
			for q in range(p+1,self.n_orb):
				gmat_pq = of.linalg.get_sparse_operator(self.orb_grad_qubit2(p,q),n_qubits=self.n_qubits)
				g_pq = state.transpose().conj().dot(gmat_pq.dot(state))
				assert(np.isclose(g_pq.imag,0))
				grad.append(g_pq.real)
		return np.array(grad)

	def orb_grad_qk(self):
		# use converged VQE results to calculate orbital gradient
		grad = []
		for p in range(0,self.n_orb):
			for q in range(p+1,self.n_orb):
				grad_pq_dict = of2qiskit(self.orb_grad_qubit2(p,q),self.n_qubits)
				grad_pq = 0.0  
				for word, weight in grad_pq_dict.items():
					grad_pq += weight*self.evs[word]
				grad.append(grad_pq)
		return grad

	def orb_hess_qk(self, diag:bool=False):
		hess_dim = (self.n_orb*self.n_orb - self.n_orb)//2
		hess = np.zeros((hess_dim,hess_dim))
		if(not(diag)): 
			pq = 0 
			for p in range(0,self.n_orb):
				for q in range(p+1,self.n_orb):
					rs = 0
					for r in range(0,self.n_orb):
						for s in range(r+1,self.n_orb):
							if(rs < pq):
								rs += 1
								continue
							hess_pqrs_dict = of2qiskit(self.orb_hess_qubit2(p,q,r,s),self.n_qubits)
							hess_pqrs = 0.0
							for word, weight in hess_pqrs_dict.items():
								hess_pqrs += weight*self.evs[word]
							hess[pq,rs] = hess_pqrs  
							hess[rs,pq] = hess_pqrs  
							# print("%d, %d, %d, %d, %.12f"%(p,q,r,s,hess_pqrs))
							rs += 1
					pq += 1
		else:
			pq = 0
			for p in range(0,self.n_orb):
				for q in range(p+1,self.n_orb):
					hess_pqpq_dict = of2qiskit(self.orb_hess_qubit2(p,q,p,q),self.n_qubits)
					hess_pqpq = 0.0 
					for word, weight in hess_pqpq_dict.items():
						hess_pqpq += weight*self.evs[word]
					hess[pq,pq] = hess_pqpq
					pq +=1
		return hess

	def orb_grad_fd(self, params:list, step:float=1e-4):
		state = self.prepare_state(params)
		grad = []
		for p in range(0,self.n_orb):
			for q in range(p+1,self.n_orb):
				kmat_f = np.zeros((self.n_orb,self.n_orb))
				kmat_f[p,q] = step
				kmat_f[q,p] = -step
				umat_f = scipy.linalg.expm(kmat_f)
				self.rotate_orbitals(umat_f)
				e_f = self.energy(params)
				kmat_b = np.zeros((self.n_orb,self.n_orb))
				kmat_b[p,q] = -2*step
				kmat_b[q,p] = 2*step
				umat_b = scipy.linalg.expm(kmat_b)
				self.rotate_orbitals(umat_b)
				e_b = self.energy(params)
				self.rotate_orbitals(umat_f)
				grad_pq = (e_f-e_b)/(2*step)
				grad.append(grad_pq)
		return np.array(grad) 

	def orb_hess(self,params:list,diag:bool=False):
		state = self.prepare_state(params)
		hess_dim = (self.n_orb*self.n_orb-self.n_orb)//2
		hess = np.zeros((hess_dim,hess_dim))
		if(not(diag)):
			pq = 0
			for p in range(0,self.n_orb):
				for q in range(p+1,self.n_orb):
					rs = 0
					for r in range(0,self.n_orb):
						for s in range(r+1,self.n_orb):
							if(rs < pq):
								rs += 1
								continue 
							hessmat_pqrs = of.linalg.get_sparse_operator(self.orb_hess_qubit2(p,q,r,s),n_qubits=self.n_qubits)
							hess_pqrs = state.transpose().conj().dot(hessmat_pqrs.dot(state))
							assert(np.isclose(hess_pqrs.imag,0))
							hess[pq,rs] = hess_pqrs.real
							hess[rs,pq] = hess_pqrs.real  
							# print("%d %d %d %d : %e"%(p,q,r,s,hess_pqrs.real))
							rs += 1
					pq += 1
		else:
			pq = 0
			for p in range(0,self.n_orb):
				for q in range(p+1,self.n_orb):
					if(diag):
						hessmat_pqpq = of.linalg.get_sparse_operator(self.orb_hess_qubit2(p,q,p,q),n_qubits=self.n_qubits)
						hess_pqpq = state.transpose().conj().dot(hessmat_pqpq.dot(state))
						assert(np.isclose(hess_pqpq.imag,0))
						hess[pq,pq] = hess_pqpq.real 
						pq += 1 
		return hess

		def optimize_orbs_qk(self,params,diag=False,alpha=1.0,grad_norm_thresh=1e-12,maxiter=50):
			curr_e = self.energy(params)
			curr_grad = self.orb_grad(params)
			grad_norm = scipy.linalg.norm(curr_grad)

			if(abs(grad_norm)>grad_norm_thresh):
				print("-----------------------------------------------------")
				print(" Iter     Energy           Difference  Orb Grad Norm ")
				print("-----------------------------------------------------")
				print("    0   %16.10f           --   %10.5e"%(curr_e,grad_norm))
			for n_iter in range(0,maxiter):
				# check for convergence before doing anything 
				converged = False
				if(abs(grad_norm)<grad_norm_thresh):
					converged = True

				if(converged):
					print("-----------------------------------------------------")
					print("Orbital optimization converged!")
					print("Optimized energy = %.15f"%curr_e)
					break

				# compute Hessian for Newton-Raphson step
				curr_hess = self.orb_hess(params,diag=diag)
				# compute NR step
				inv_hess = scipy.linalg.inv(curr_hess)
				k = -alpha*inv_hess.dot(curr_grad)
				# build and exponentiate kappa matrix
				kmat = np.zeros((self.n_orb,self.n_orb))
				pq = 0
				for p in range(0,self.n_orb):
					for q in range(p+1,self.n_orb):
						kmat[p,q] =  k[pq]
						kmat[q,p] = -k[pq]
						pq += 1 
				u = scipy.linalg.expm(kmat)
				#assert(np.isclose(u.transpose().conj().dot(u),np.eye(n_orb)))
				self.rotate_orbitals(u)
				# ham_mat = of.linalg.get_sparse_operator(self.ham_qop(),n_qubits=n_orb)
				# e,v = scipy.sparse.linalg.eigsh(ham_mat, k=1, which="SA")
				# print("DOCI = %.15f"%e)
				new_e = self.energy(params)
				curr_grad = self.orb_grad(params)
				grad_norm = scipy.linalg.norm(curr_grad)
				print(" %4d   %16.10f  %10.5e  %10.5e"%((n_iter+1),new_e,(new_e-curr_e),grad_norm))
				curr_e = new_e

	def orb_hess_fd(self, params:list, step:float=1e-4):
		hess_dim = (self.n_orb*self.n_orb-self.n_orb)//2
		hess_fd = np.zeros((hess_dim,hess_dim))
		pq = 0 
		for p in range(0,self.n_orb):
			for q in range(p+1,self.n_orb):
				rs = 0
				for r in range(0,self.n_orb):
					for s in range(r+1,self.n_orb):
						if(rs < pq):
							rs += 1 
							continue
						# e_0 = self.energy(params)
						# print("Starting energy  : %.15f"%e_0)
						# ff
						kmat_ff = np.zeros((self.n_orb,self.n_orb))
						kmat_ff[p,q] = step
						kmat_ff[q,p] = -step
						kmat_ff[r,s] += step
						kmat_ff[s,r] -= step
						umat_ff = scipy.linalg.expm(kmat_ff)
						self.rotate_orbitals(umat_ff)
						e_ff = self.energy(params)
						self.rotate_orbitals(umat_ff.transpose())
						# e_0 = self.energy(params)
						# print("Starting energy? : %.15f"%e_0)
						# fb
						kmat_fb = np.zeros((self.n_orb,self.n_orb))
						kmat_fb[p,q] = step 
						kmat_fb[q,p] = -step
						kmat_fb[r,s] -= step 
						kmat_fb[s,r] += step
						umat_fb = scipy.linalg.expm(kmat_fb)
						self.rotate_orbitals(umat_fb)
						e_fb = self.energy(params) 
						self.rotate_orbitals(umat_fb.transpose())
						# bf
						kmat_bf = np.zeros((self.n_orb,self.n_orb))
						kmat_bf[p,q] = -step
						kmat_bf[q,p] = step
						kmat_bf[r,s] += step
						kmat_bf[s,r] -= step
						umat_bf = scipy.linalg.expm(kmat_bf)
						self.rotate_orbitals(umat_bf)
						e_bf = self.energy(params) 
						self.rotate_orbitals(umat_bf.transpose())
						# bb
						kmat_bb = np.zeros((self.n_orb,self.n_orb))
						kmat_bb[p,q] = -step
						kmat_bb[q,p] = step
						kmat_bb[r,s] -= step
						kmat_bb[s,r] += step
						umat_bb = scipy.linalg.expm(kmat_bb)
						self.rotate_orbitals(umat_bb)
						e_bb = self.energy(params)
						self.rotate_orbitals(umat_bb.transpose())
						# compute hessian term
						hess_fd_pqrs = (e_ff - e_fb - e_bf + e_bb)/(4.0*step*step)
						hess_fd[pq,rs] = hess_fd_pqrs
						hess_fd[rs,pq] = hess_fd_pqrs
						# e_0 = self.energy(params)
						# print("Starting energy? : %.15f"%e_0)
						print("%d %d %d %d %e"%(p,q,r,s,hess_fd_pqrs))
						rs += 1
				pq += 1 
		return hess_fd

	def orb_hess_fd_element(self, p:int, q:int, r:int, s:int, params:list, step:float=1e-4):
		e_0 = self.energy(params)
		print("Starting energy  : %.15f"%e_0)
		# ff
		kmat_ff = np.zeros((self.n_orb,self.n_orb))
		kmat_ff[p,q] = step
		kmat_ff[q,p] = -step
		kmat_ff[r,s] += step
		kmat_ff[s,r] -= step
		umat_ff = scipy.linalg.expm(kmat_ff)
		self.rotate_orbitals(umat_ff)
		e_ff = self.energy(params)
		self.rotate_orbitals(umat_ff.transpose())
		e_0 = self.energy(params)
		print("Starting energy? : %.15f"%e_0)
		# fb
		kmat_fb = np.zeros((self.n_orb,self.n_orb))
		kmat_fb[p,q] = step 
		kmat_fb[q,p] = -step
		kmat_fb[r,s] -= step 
		kmat_fb[s,r] += step
		umat_fb = scipy.linalg.expm(kmat_fb)
		self.rotate_orbitals(umat_fb)
		e_fb = self.energy(params) 
		self.rotate_orbitals(umat_fb.transpose())
		e_0 = self.energy(params)
		print("Starting energy? : %.15f"%e_0)
		# bf
		kmat_bf = np.zeros((self.n_orb,self.n_orb))
		kmat_bf[p,q] = -step
		kmat_bf[q,p] = step
		kmat_bf[r,s] += step
		kmat_bf[s,r] -= step
		umat_bf = scipy.linalg.expm(kmat_bf)
		self.rotate_orbitals(umat_bf)
		e_bf = self.energy(params) 
		self.rotate_orbitals(umat_bf.transpose())
		e_0 = self.energy(params)
		print("Starting energy? : %.15f"%e_0)
		# bb
		kmat_bb = np.zeros((self.n_orb,self.n_orb))
		kmat_bb[p,q] = -step
		kmat_bb[q,p] = step
		kmat_bb[r,s] -= step
		kmat_bb[s,r] += step
		umat_bb = scipy.linalg.expm(kmat_bb)
		self.rotate_orbitals(umat_bb)
		e_bb = self.energy(params)
		self.rotate_orbitals(umat_bb.transpose())
		# compute hessian term
		hess_fd_pqrs = (e_ff - e_fb - e_bf + e_bb)/(4.0*step*step)
		e_0 = self.energy(params)
		print("Starting energy? : %.15f"%e_0)
		return hess_fd_pqrs, e_ff, e_fb, e_bf, e_bb
	
	def optimize_orbs(self,params:list,diag:bool=False,alpha:float=0.01,grad_norm_thresh:float=1e-10,maxiter:int=500):
		curr_e = self.energy(params)
		curr_grad = self.orb_grad(params)
		grad_norm = scipy.linalg.norm(curr_grad)

		if(abs(grad_norm)>grad_norm_thresh):
			print("-----------------------------------------------------")
			print(" Iter     Energy           Difference  Orb Grad Norm ")
			print("-----------------------------------------------------")
			print("    0   %16.10f           --   %10.5e"%(curr_e,grad_norm))
		for n_iter in range(0,maxiter):
			# check for convergence before doing anything 
			converged = False
			if(abs(grad_norm)<grad_norm_thresh):
				converged = True

			if(converged):
				print("-----------------------------------------------------")
				print("Orbital optimization converged!")
				print("Optimized energy = %.15f"%curr_e)
				break

			# compute Hessian for Newton-Raphson step
			curr_hess = self.orb_hess(params,diag=diag)
			# compute NR step
			try:
				inv_hess = scipy.linalg.inv(curr_hess)
			except:
				k = -0.01*curr_grad
			else:
				k = -alpha*inv_hess.dot(curr_grad)
			# build and exponentiate kappa matrix
			kmat = np.zeros((self.n_orb,self.n_orb))
			pq = 0
			for p in range(0,self.n_orb):
				for q in range(p+1,self.n_orb):
					kmat[p,q] =  k[pq]
					kmat[q,p] = -k[pq]
					pq += 1 
			u = scipy.linalg.expm(kmat)
			#assert(np.isclose(u.transpose().conj().dot(u),np.eye(n_orb)))
			self.rotate_orbitals(u)
			# ham_mat = of.linalg.get_sparse_operator(self.ham_qop(),n_qubits=n_orb)
			# e,v = scipy.sparse.linalg.eigsh(ham_mat, k=1, which="SA")
			# print("DOCI = %.15f"%e)
			new_e = self.energy(params)
			curr_grad = self.orb_grad(params)
			grad_norm = scipy.linalg.norm(curr_grad)
			print(" %4d   %16.10f  %10.5e  %10.5e"%((n_iter+1),new_e,(new_e-curr_e),grad_norm))
			curr_e = new_e

		if(not(converged)):
			print("-----------------------------------------------------")
			print("Orbital optimization failed after %d iteration!"%(n_iter+1))
			print("Unconverged energy = %.15f"%curr_e)
		self.curr_e = new_e	
		return curr_e

	def optimize_orbs_qk(self,diag:bool=False,alpha:float=0.01,grad_norm_thresh:float=1e-10,maxiter:int=1000):
		curr_e = self.expected_energy()
		curr_grad = self.orb_grad_qk()
		grad_norm = scipy.linalg.norm(curr_grad)

		if(abs(grad_norm)>grad_norm_thresh):
			print("-----------------------------------------------------")
			print(" Iter     Energy           Difference  Orb Grad Norm ")
			print("-----------------------------------------------------")
			print("    0   %16.10f           --   %10.5e"%(curr_e,grad_norm))
		for n_iter in range(0,maxiter):
			# check for convergence before doing anything 
			converged = False
			if(abs(grad_norm)<grad_norm_thresh):
				converged = True

			if(converged):
				print("-----------------------------------------------------")
				print("Orbital optimization converged!")
				print("Optimized energy = %.15f"%curr_e)
				break

			# compute Hessian for Newton-Raphson step
			curr_hess = self.orb_hess_qk(diag=diag)
			# compute NR step
			try:
				inv_hess = scipy.linalg.inv(curr_hess)
			except:
				print("Singular Hessian! Switching to gradient descent with learning rate = %f"%alpha)
				k = -alpha*np.array(curr_grad)
			else:
				k = -inv_hess.dot(curr_grad)
			# build and exponentiate kappa matrix
			kmat = np.zeros((self.n_orb,self.n_orb))
			pq = 0
			for p in range(0,self.n_orb):
				for q in range(p+1,self.n_orb):
					kmat[p,q] =  k[pq]
					kmat[q,p] = -k[pq]
					pq += 1 
			u = scipy.linalg.expm(kmat)
			#assert(np.isclose(u.transpose().conj().dot(u),np.eye(n_orb)))
			self.rotate_orbitals(u)
			# ham_mat = of.linalg.get_sparse_operator(self.ham_qop(),n_qubits=n_orb)
			# e,v = scipy.sparse.linalg.eigsh(ham_mat, k=1, which="SA")
			# print("DOCI = %.15f"%e)
			new_e = self.expected_energy()
			curr_grad = self.orb_grad_qk()
			grad_norm = scipy.linalg.norm(curr_grad)
			print(" %4d   %16.10f  %10.5e  %10.5e"%((n_iter+1),new_e,(new_e-curr_e),grad_norm))
			curr_e = new_e

		if(not(converged)):
			print("-----------------------------------------------------")
			print("Orbital optimization failed after %d iteration!"%(n_iter+1))
			print("Unconverged energy = %.15f"%curr_e)
		self.curr_e = new_e	
		return curr_e

	def orb_hess_fd2(self, params:list, step:float=1e-4):
		"""
		Computes the finite difference Hessian matrix using a second-order central differences
		formula to test analytic implementation
		"""
		# initialize Hessian matrix
		hess_dim = (self.n_orb*self.n_orb - self.n_orb)//2
		hess = np.zeros((hess_dim,hess_dim))
		pq = 0
		for p in range(0, self.n_orb):
			for q in range(p+1,self.n_orb):
				rs = 0
				for r in range(0,self.n_orb):
					for s in range(r+1,self.n_orb):
						if (rs < pq):
							rs += 1
							continue
						# e_0 = self.energy(params)
						# print("Starting energy : %.15f"%e_0)
						# ff
						kmat_ff = np.zeros((self.n_orb,self.n_orb))
						kmat_ff[p,q] = step
						kmat_ff[q,p] = -step
						kmat_ff[r,s] += step
						kmat_ff[s,r] -= step
						umat_ff = scipy.linalg.expm(kmat_ff)
						self.rotate_orbitals(umat_ff)
						e_ff = self.energy(params)
						# fb
						kmat_fb = np.zeros((self.n_orb,self.n_orb))
						kmat_fb[r,s] = -2*step
						kmat_fb[s,r] = 2*step
						umat_fb = scipy.linalg.expm(kmat_fb)
						self.rotate_orbitals(umat_fb)
						e_fb = self.energy(params)
						# bf
						kmat_bf = np.zeros((self.n_orb,self.n_orb))
						kmat_bf[p,q] = -2*step
						kmat_bf[q,p] = 2*step
						kmat_bf[r,s] += 2*step
						kmat_bf[s,r] += -2*step
						umat_bf = scipy.linalg.expm(kmat_bf)
						self.rotate_orbitals(umat_bf)
						e_bf = self.energy(params)
						# bb
						kmat_bb = np.zeros((self.n_orb,self.n_orb))
						kmat_bb[r,s] = -2*step
						kmat_bb[s,r] = 2*step
						umat_bb = scipy.linalg.expm(kmat_bb)
						self.rotate_orbitals(umat_bb)
						e_bb = self.energy(params)
						# revert changes to integrals
						self.rotate_orbitals(umat_ff)
						hess_fd_pqrs = (e_ff - e_fb - e_bf + e_bb)/(4.0*step*step)
						hess[pq,rs] = hess_fd_pqrs
						hess[rs,pq] = hess_fd_pqrs
						# e_0 = self.energy(params)
						# print("Starting energy? : %.15f"%e_0)
						rs += 1
				pq += 1
		return hess

	def orb_hess_fd2_element(self, p:int, q:int, r:int, s:int, params:list, step:float=1e-4):
		# e_0 = self.energy(params)
		# print("Starting energy : %.15f"%e_0)
		# ff
		kmat_ff = np.zeros((self.n_orb,self.n_orb))
		kmat_ff[p,q] = step
		kmat_ff[q,p] = -step
		kmat_ff[r,s] += step
		kmat_ff[s,r] -= step
		umat_ff = scipy.linalg.expm(kmat_ff)
		self.rotate_orbitals(umat_ff)
		e_ff = self.energy(params)
		# fb
		kmat_fb = np.zeros((self.n_orb,self.n_orb))
		kmat_fb[r,s] = -2*step
		kmat_fb[s,r] = 2*step
		umat_fb = scipy.linalg.expm(kmat_fb)
		self.rotate_orbitals(umat_fb)
		e_fb = self.energy(params)
		# bf
		kmat_bf = np.zeros((self.n_orb,self.n_orb))
		kmat_bf[p,q] = -2*step
		kmat_bf[q,p] = 2*step
		kmat_bf[r,s] += 2*step
		kmat_bf[s,r] += -2*step
		umat_bf = scipy.linalg.expm(kmat_bf)
		self.rotate_orbitals(umat_bf)
		e_bf = self.energy(params)
		# bb
		kmat_bb = np.zeros((self.n_orb,self.n_orb))
		kmat_bb[r,s] = -2*step
		kmat_bb[s,r] = 2*step
		umat_bb = scipy.linalg.expm(kmat_bb)
		self.rotate_orbitals(umat_bb)
		e_bb = self.energy(params)
		# revert changes to integrals
		self.rotate_orbitals(umat_ff)
		hess_fd_pqrs = (e_ff - e_fb - e_bf + e_bb)/(4.0*step*step)
		# e_0 = self.energy(params)
		# print("Starting energy? : %.15f"%e_0)
		return hess_fd_pqrs, e_ff, e_fb, e_bf, e_bb 

	def optimize_ansatz(self, params:list, maxiter_macro:int=20, thresh_macro:float=1e-7, thresh_amps:float=1e-5, 
						maxiter_amps:int=50, thresh_orbs:float=1e-10, maxiter_orbs:int=100, alpha:float=0.01, diag:bool=False):
		iter_macro = 0
		print("OO-VQE Macro-iteration:", iter_macro)
		old_e = self.energy(params)
		self.optimize_amps(params, thresh=thresh_amps)
		self.optimize_orbs(self.vqe_params,diag=diag,alpha=alpha,grad_norm_thresh=thresh_orbs,maxiter=maxiter_orbs)
		new_e = self.curr_e
		iter_macro += 1
		while(iter_macro<maxiter_macro):
			converged = False
			if(abs(new_e-old_e)<thresh_macro):
				converged = True
			if(converged):
				print("OO-VQE optimization converged!")
				print("Converged energy: %.15f"%self.curr_e)
				break 
			print("OO-VQE Macro-iteration:", iter_macro)
			old_e = self.curr_e
			self.optimize_amps(self.vqe_params,thresh=thresh_amps)
			self.optimize_orbs(self.vqe_params,diag=diag,alpha=alpha,grad_norm_thresh=thresh_orbs,maxiter=maxiter_orbs)
			new_e = self.curr_e 
			iter_macro += 1 

		if(not(converged)):
			print("OO-VQE optimization failed to converge after %d iterations!"%iter_macro)
			print("Unconverged energy %.15f"%self.curr_e)
		return self.curr_e

	def optimize_ansatz_qk(self, params:list, maxiter_macro:int=20, thresh_macro:float=1e-7, thresh_amps:float=1e-5, 
						maxiter_amps:int=1000, thresh_orbs:float=1e-10, maxiter_orbs:int=1000, alpha:float=0.01, diag:bool=False):
		iter_macro = 0
		converged = False
		print("OO-VQE Macro-iteration:", iter_macro)
		old_e = self.compute_energy_qk(params)
		self.optimize_amps_qk(params, thresh=thresh_amps, maxiter_amps=maxiter_amps)
		self.optimize_orbs_qk(diag=diag,alpha=alpha,grad_norm_thresh=thresh_orbs,maxiter=maxiter_orbs)
		new_e = self.curr_e
		iter_macro += 1
		while(iter_macro<maxiter_macro):
			converged = False
			if(abs(new_e-old_e)<thresh_macro):
				converged = True
			if(converged):
				print("OO-VQE optimization converged!")
				print("Converged energy: %.15f"%self.curr_e)
				break 
			print("OO-VQE Macro-iteration:", iter_macro)
			old_e = self.curr_e
			self.optimize_amps_qk(self.vqe_params,thresh=thresh_amps, maxiter_amps=maxiter_amps)
			self.optimize_orbs_qk(diag=diag,alpha=alpha,grad_norm_thresh=thresh_orbs,maxiter=maxiter_orbs)
			new_e = self.curr_e 
			iter_macro += 1 

		if(not(converged)):
			print("OO-VQE optimization failed to converge after %d iterations!"%iter_macro)
			print("Unconverged energy %.15f"%self.curr_e)
		return self.curr_e
#}

# print("START TESTING")
# ref_vec = of.linalg.jw_configuration_state(list([1,3]),10)
# print(scipy.sparse.csc_matrix(ref_vec))
# exdex = of.QubitOperator()
# exdex += of.QubitOperator(((3,'X'),(0,'Y')),  0.5j)
# exdex += of.QubitOperator(((0,'X'),(3,'Y')), -0.5j)
# exdex_op = of.linalg.get_sparse_operator(exdex, 10)
# vec = exdex_op.dot(ref_vec)
# print(scipy.sparse.csc_matrix(vec))
# exit()

# oovqe = pairUCC(n_a,h1mo,h2mo,e_nuc,frozen_orbs=None)
# print(oovqe.active_mask)
# print(oovqe.n_qubits)
# print(scipy.sparse.csc_matrix(oovqe.ref))
# print("Initial energy")
# print(oovqe.energy(oovqe.vqe_params))
# ham = of.linalg.get_sparse_operator(oovqe.ham_qubit(),n_qubits=oovqe.n_qubits)
# e,v = scipy.sparse.linalg.eigsh(ham.real, k=1, which='SA', v0=oovqe.ref)
# print("DOCI : ", e[0])
# oovqe.optimize_ansatz(oovqe.vqe_params)
# print("Optimizer")
#oovqe.optimize_amps(oovqe.vqe_params)
# print(oovqe.initial_guess_mp2d())
# ham, obs, weights = of2qiskit(oovqe.ham_qubit(),oovqe.n_qubits)
# print(ham)
# print(obs)
# print(weights)
# exit()
# print(of2qiskit(oovqe.ham_qubit(),oovqe.n_qubits)[0])
# exit()
# ansatz = oovqe.givens_rot_ansatz()
# ansatz.draw(output='mpl',filename='givens.jpeg')
# oovqe.optimize_ansatz_qk(oovqe.initial_guess_mp2d())
# exit()

