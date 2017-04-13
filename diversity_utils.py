import numpy
from scipy.linalg import eigh
from scipy.cluster.hierarchy import dendrogram, linkage
from scipy.cluster.hierarchy import cophenet
from scipy.cluster.hierarchy import fcluster
 

# Calls consensus genotypes from matrix of allele counts
#
# Returns: genotype matrix, passed_sitse matrix for polymorphic sites
#
def calculate_consensus_genotypes(allele_counts_matrix):
    
    num_sites, num_samples, num_alleles = allele_counts_matrix.shape
    
    depths = allele_counts_matrix.sum(axis=2)
    freqs = allele_counts_matrix[:,:,0]*1.0/(depths+(depths==0))
    passed_sites_matrix = (depths>0)
    # consensus approximation
    genotype_matrix = numpy.around(freqs)
    
    prevalences = genotype_matrix.sum(axis=1)
    min_prevalences = 0.5
    max_prevalences = (passed_sites_matrix).sum(axis=1)-0.5
    
    polymorphic_sites = (prevalences>min_prevalences)*(prevalences<max_prevalences)
    
    return genotype_matrix[polymorphic_sites,:], passed_sites_matrix[polymorphic_sites,:]
    

# Calculates first two PCA coordinates for samples in allele_counts
# using the normalization scheme outlined in McVean (PLoS Genet, 2009).
#
# Returns: (vector of pca1 coords, vector of pca2 coords), (percent variance 1, percent variance 2)
#
def calculate_pca_coordinates(genotype_matrix, passed_sites_matrix):

    Zl = (genotype_matrix*passed_sites_matrix).sum(axis=1)/(passed_sites_matrix).sum(axis=1)

    Zli = (genotype_matrix-Zl[:,None])*passed_sites_matrix
    
    Mij = numpy.einsum('li,lj',Zli,Zli)/numpy.einsum('li,lj',passed_sites_matrix, passed_sites_matrix)

    # calculate eigenvectors & eigenvalues of the covariance matrix
    # use 'eigh' rather than 'eig' since R is symmetric, 
    # the performance gain is substantial
    evals, evecs = eigh(Mij)

    # sort eigenvalue in decreasing order
    idx = numpy.argsort(evals)[::-1]
    evals = evals[idx]
    evecs = evecs[:,idx]
    
    variances = evals/evals.sum()
    
    pca1_coords = evals[0]**0.5*evecs[:,0]
    pca2_coords = evals[1]**0.5*evecs[:,1]
    
    return (pca1_coords, pca2_coords), (variances[0],variances[1])
    
 

def calculate_rsquared_condition_freq(allele_counts_1, allele_counts_2, low_freq, high_freq):
    # Note: should actually be sigma_squared! 
    # sigma_squared= E[X]/E[Y], where X=(p_ab-pa*pb)^2 and Y=(pa*(1-pa)*pb*(1-pb))
    # rsquared=E[X/Y]
    # see McVean 2002 for more notes on the difference. 

    # allele counts = 1 x samples x alleles vector
    
    depths_1 = allele_counts_1.sum(axis=2)
    freqs_1 = allele_counts_1[:,:,0]*1.0/(depths_1+(depths_1==0))
    depths_2 = allele_counts_2.sum(axis=2)
    freqs_2 = allele_counts_2[:,:,0]*1.0/(depths_2+(depths_2==0))

    
    # consensus approximation
    freqs_1 = numpy.around(freqs_1)
    freqs_2 = numpy.around(freqs_2)

    # condition on allele frequency in the pooled population:
    pooled_freqs_1=freqs_1[:,:].sum(axis=1)/len(freqs_1[0])
    pooled_freqs_2=freqs_2[:,:].sum(axis=1)/len(freqs_2[0])

    # check if any freqs >0.5, if so, fold:
    pooled_freqs_1=numpy.where(pooled_freqs_1 > 0.5, 1-pooled_freqs_1, pooled_freqs_1)
    pooled_freqs_2=numpy.where(pooled_freqs_2 > 0.5, 1-pooled_freqs_2, pooled_freqs_2) 

    # this asks which pairs of sites have depths >0 at BOTH sites as well as which paris of sites both have pooled frequencies within the low_freq and high_freq ranges. 
    # None here takes the product of the elements in the two vectors and returns a matrix. 

    
    passed_sites_1=(depths_1>0)*(pooled_freqs_1 >= low_freq)[:,None]*(pooled_freqs_1 <=high_freq)[:,None]
    passed_sites_2=(depths_2>0)*(pooled_freqs_2 >= low_freq)[:,None]*(pooled_freqs_2 <= high_freq)[:,None]
    joint_passed_sites=passed_sites_1[None,:,:]*passed_sites_2[:,None,:]
    # sites x sites x samples matrix
    
    joint_freqs = freqs_1[None,:,:]*freqs_2[:,None,:]
    # sites x sites x samples_matrix
    
    # this tells us what the denominator is for the computation below for joint_pooled_freqs
    total_joint_passed_sites = joint_passed_sites.sum(axis=2)
    # add 1 to denominator if some pair is 0. 
    total_joint_passed_sites = total_joint_passed_sites+(total_joint_passed_sites==0)
    
    # compute p_ab
    joint_pooled_freqs = (joint_freqs*joint_passed_sites).sum(axis=2)/total_joint_passed_sites   
    # floting point issue
    joint_pooled_freqs *= (joint_pooled_freqs>1e-10)
    
    # compute p_a
    marginal_pooled_freqs_1 = (freqs_1[None,:,:]*joint_passed_sites).sum(axis=2)/total_joint_passed_sites
    marginal_pooled_freqs_1 *= (marginal_pooled_freqs_1>1e-10)

    # compute p_b
    marginal_pooled_freqs_2 = (freqs_2[:,None,:]*joint_passed_sites).sum(axis=2)/total_joint_passed_sites 
    marginal_pooled_freqs_2 *= (marginal_pooled_freqs_2>1e-10)
       
    # (p_ab-p_a*p_b)^2
    rsquared_numerators = numpy.square(joint_pooled_freqs-marginal_pooled_freqs_1*marginal_pooled_freqs_2)
    
    # (p_a*(1-p_a)*pb*(1-p_b))
    rsquared_denominators = marginal_pooled_freqs_1*(1-marginal_pooled_freqs_1)*marginal_pooled_freqs_2*(1-marginal_pooled_freqs_2)


    rsquareds = rsquared_numerators/(rsquared_denominators+(rsquared_denominators==0))
    
    return rsquared_numerators, rsquared_denominators


#####################################################################

def calculate_unbiased_sigmasquared(allele_counts_1, allele_counts_2):
    
    # Note: should actually be sigma_squared! 
    # sigma_squared= E[X]/E[Y], where X=(p_ab-pa*pb)^2 and Y=(pa*(1-pa)*pb*(1-pb))
    # rsquared=E[X/Y]
    # see McVean 2002 for more notes on the difference. 

    # allele counts = 1 x samples x alleles vector
    
    depths_1 = allele_counts_1.sum(axis=2)
    freqs_1 = allele_counts_1[:,:,0]*1.0/(depths_1+(depths_1==0))
    depths_2 = allele_counts_2.sum(axis=2)
    freqs_2 = allele_counts_2[:,:,0]*1.0/(depths_2+(depths_2==0))
    
    # consensus approximation
    freqs_1 = numpy.around(freqs_1)
    freqs_2 = numpy.around(freqs_2)
    

    # this asks which pairs of sites have depths >0 at BOTH sites
    # None here takes the product of the elements in the two vectors and returns a matrix. 
    joint_passed_sites = (depths_1>0)[None,:,:]*(depths_2>0)[:,None,:]
    # sites x sites x samples matrix
    
    joint_freqs = freqs_1[None,:,:]*freqs_2[:,None,:]
    # sites x sites x samples_matrix
    
    # this tells us what the denominator is for the computation below for joint_pooled_freqs
    total_joint_passed_sites = joint_passed_sites.sum(axis=2)
    # add 1 to denominator if some pair is 0. 
    total_joint_passed_sites = total_joint_passed_sites+(total_joint_passed_sites==0)
    
    # compute p_ab
    joint_pooled_freqs = (joint_freqs*joint_passed_sites).sum(axis=2)/total_joint_passed_sites   
    # floting point issue
    joint_pooled_freqs *= (joint_pooled_freqs>1e-10)
    
    # compute p_a
    marginal_pooled_freqs_1 = (freqs_1[None,:,:]*joint_passed_sites).sum(axis=2)/total_joint_passed_sites
    marginal_pooled_freqs_1 *= (marginal_pooled_freqs_1>1e-10)

    # compute p_b
    marginal_pooled_freqs_2 = (freqs_2[:,None,:]*joint_passed_sites).sum(axis=2)/total_joint_passed_sites 
    marginal_pooled_freqs_2 *= (marginal_pooled_freqs_2>1e-10)
       
    # (p_ab-p_a*p_b)^2
    rsquared_numerators = numpy.square(joint_pooled_freqs-marginal_pooled_freqs_1*marginal_pooled_freqs_2)
    
    # (p_a*(1-p_a)*pb*(1-p_b))
    rsquared_denominators = marginal_pooled_freqs_1*(1-marginal_pooled_freqs_1)*marginal_pooled_freqs_2*(1-marginal_pooled_freqs_2)
    
    rsquareds = rsquared_numerators/(rsquared_denominators+(rsquared_denominators==0))
    
    return rsquared_numerators, rsquared_denominators


#####################################################################

def calculate_rsquared(allele_counts_1, allele_counts_2):
    # Note: should actually be sigma_squared! 
    # sigma_squared= E[X]/E[Y], where X=(p_ab-pa*pb)^2 and Y=(pa*(1-pa)*pb*(1-pb))
    # rsquared=E[X/Y]
    # see McVean 2002 for more notes on the difference. 

    # allele counts = 1 x samples x alleles vector
    
    depths_1 = allele_counts_1.sum(axis=2)
    freqs_1 = allele_counts_1[:,:,0]*1.0/(depths_1+(depths_1==0))
    depths_2 = allele_counts_2.sum(axis=2)
    freqs_2 = allele_counts_2[:,:,0]*1.0/(depths_2+(depths_2==0))

    
    # consensus approximation
    freqs_1 = numpy.around(freqs_1)
    freqs_2 = numpy.around(freqs_2)
    

    # this asks which pairs of sites have depths >0 at BOTH sites
    # None here takes the product of the elements in the two vectors and returns a matrix. 
    joint_passed_sites = (depths_1>0)[None,:,:]*(depths_2>0)[:,None,:]
    # sites x sites x samples matrix
    
    joint_freqs = freqs_1[None,:,:]*freqs_2[:,None,:]
    # sites x sites x samples_matrix
    
    # this tells us what the denominator is for the computation below for joint_pooled_freqs
    total_joint_passed_sites = joint_passed_sites.sum(axis=2)
    # add 1 to denominator if some pair is 0. 
    total_joint_passed_sites = total_joint_passed_sites+(total_joint_passed_sites==0)
    
    # compute p_ab
    joint_pooled_freqs = (joint_freqs*joint_passed_sites).sum(axis=2)/total_joint_passed_sites   
    # floting point issue
    joint_pooled_freqs *= (joint_pooled_freqs>1e-10)
    
    # compute p_a
    marginal_pooled_freqs_1 = (freqs_1[None,:,:]*joint_passed_sites).sum(axis=2)/total_joint_passed_sites
    marginal_pooled_freqs_1 *= (marginal_pooled_freqs_1>1e-10)

    # compute p_b
    marginal_pooled_freqs_2 = (freqs_2[:,None,:]*joint_passed_sites).sum(axis=2)/total_joint_passed_sites 
    marginal_pooled_freqs_2 *= (marginal_pooled_freqs_2>1e-10)
       
    # (p_ab-p_a*p_b)^2
    rsquared_numerators = numpy.square(joint_pooled_freqs-marginal_pooled_freqs_1*marginal_pooled_freqs_2)
    
    # (p_a*(1-p_a)*pb*(1-p_b))
    rsquared_denominators = marginal_pooled_freqs_1*(1-marginal_pooled_freqs_1)*marginal_pooled_freqs_2*(1-marginal_pooled_freqs_2)
    
    rsquareds = rsquared_numerators/(rsquared_denominators+(rsquared_denominators==0))
    
    return rsquared_numerators, rsquared_denominators





##################################
def generate_haplotype(allele_counts_4D, allele_counts_1D, location_dictionary, species_name):

    freqs={}

    depths_4D = allele_counts_4D.sum(axis=2)
    freqs['4D'] = allele_counts_4D[:,:,0]*1.0/(depths_4D+(depths_4D==0))

    depths_1D = allele_counts_1D.sum(axis=2)
    freqs['1D'] = allele_counts_1D[:,:,0]*1.0/(depths_1D+(depths_1D==0))

    #explanation of numpy commands above:
    # allele_counts_1.sum(axis=2) this returns a sum over all sites alt + ref counts. 
    #(depths_1+(depths_1==0) this is done because if depths_1==0, then we've have a division error. addition of 1 when depths_1==0. 
    #allele_counts_1[:,:,0] means that the alt allele is grabbed. Multiply by 1.0 to convert to float
    
    # consensus approximation
    consensus={}
    consensus['4D'] = numpy.around(freqs['4D'])
    consensus['1D'] = numpy.around(freqs['1D'])
    

    locations=location_dictionary.keys()
    locations=sorted(locations)
   
    #s_consensus='' # store the haplotypes in a string for printing out later
    #s_annotation=''
    outFile_consensus=open('tmp_consensus_%s.txt' % species_name ,'w')
    outFile_anno=open('tmp_anno_%s.txt' % species_name ,'w')

    for loc in range(0, len(locations)):
        location=str(int(locations[loc])) 
        index=location_dictionary[locations[loc]][0]
        variant_type=location_dictionary[locations[loc]][1]
        alleles=consensus[variant_type][index].tolist()
        annotation=freqs[variant_type][index].tolist()

        for person in range(0, len(alleles)):
            alleles[person]=str(int(alleles[person]))
            if annotation[person] ==0:
                annotation[person]=str(0) # no difference from ref
            elif annotation[person] ==1:
                if variant_type=='4D':
                    annotation[person]=str(1) # fixed syn diff from ref
                else:
                    annotation[person]=str(2) # fixed nonsyn diff from ref
            else: 
                if variant_type=='4D':
                    annotation[person]=str(3) # polymorphic syn within host
                else:
                    annotation[person]=str(4) # polymorphic nonsyn within host
        s_consensus = location + ',' + ','.join(alleles) +'\n' 
        s_annotation = location + ',' + ','.join(annotation) + '\n'
        outFile_consensus.write(s_consensus)
        outFile_anno.write(s_annotation)

    return [s_consensus, s_annotation]

####################################

def calculate_sample_freqs(allele_counts_map, passed_sites_map, variant_type='4D', allowed_genes=None, fold=True):

    if allowed_genes == None:
        allowed_genes = set(passed_sites_map.keys())
     
    sample_freqs = [[] for i in xrange(0,allele_counts_map[allele_counts_map.keys()[0]][variant_type]['alleles'].shape[1])]
    
    passed_sites = numpy.zeros(passed_sites_map[passed_sites_map.keys()[0]][variant_type]['sites'].shape[0])*1.0
    
    for gene_name in allowed_genes:
    
        allele_counts = allele_counts_map[gene_name][variant_type]['alleles']

        if len(allele_counts)==0:
            continue
            
        depths = allele_counts.sum(axis=2)
        freqs = allele_counts[:,:,0]/(depths+(depths==0))
        if fold == True:
            freqs = numpy.fmin(freqs,1-freqs) #fold
        for sample_idx in xrange(0,freqs.shape[1]):
            gene_freqs = freqs[:,sample_idx]
            sample_freqs[sample_idx].extend( gene_freqs[gene_freqs>0])
            
        passed_sites += numpy.diagonal(passed_sites_map[gene_name][variant_type]['sites'])
        
    
    return sample_freqs, passed_sites




####################################

def calculate_sample_freqs_2D(allele_counts_map, passed_sites_map, desired_samples, variant_type='4D', allowed_genes=None, fold=True):

    
    if allowed_genes == None:
        allowed_genes = set(passed_sites_map.keys())
     
    num_samples=sum(desired_samples)
    sample_freqs = [[] for i in xrange(0, num_samples)]
    joint_passed_sites= [[] for i in xrange(0, num_samples)]
    passed_sites = numpy.zeros((num_samples, num_samples))*1.0
    

    for gene_name in allowed_genes:

        allele_counts = allele_counts_map[gene_name][variant_type]['alleles']

        if len(allele_counts)==0:
            continue

        allele_counts = allele_counts[:,desired_samples,:]            
        depths = allele_counts.sum(axis=2)
        freqs = allele_counts[:,:,0]*1.0/(depths+(depths==0))
        joint_passed_sites_tmp=(depths>0)[:,None,:]*(depths>0)[:,:,None]

        if fold== True:
            freqs = numpy.fmin(freqs,1-freqs) 
        
        for sample_idx in xrange(0,freqs.shape[1]):
            gene_freqs = freqs[:,sample_idx]
            sample_freqs[sample_idx].extend(gene_freqs)
            joint_passed_sites[sample_idx].extend(joint_passed_sites_tmp[:,0,sample_idx])
            idx=numpy.where(desired_samples==True)
        passed_sites += passed_sites_map[gene_name][variant_type]['sites'][:,idx[0]][idx[0],:]
    
    return sample_freqs, passed_sites, joint_passed_sites

####################
        
def calculate_pooled_freqs(allele_counts_map, passed_sites_map,  variant_type='4D', allowed_genes=None):

    if allowed_genes == None:
        allowed_genes = set(passed_sites_map.keys())
     
    pooled_freqs = []
    
    for gene_name in allowed_genes:
        
        allele_counts = allele_counts_map[gene_name][variant_type]['alleles']
        
        if len(allele_counts)==0:
            continue
            
        depths = allele_counts.sum(axis=2)
        freqs = allele_counts/(depths+(depths==0))[:,:,None]
        gene_pooled_freqs = freqs[:,:,0].sum(axis=1)/(depths>0).sum(axis=1)
        pooled_freqs.extend(gene_pooled_freqs)

    pooled_freqs = numpy.array(pooled_freqs)
    return pooled_freqs



def calculate_fixation_matrix(allele_counts_map, passed_sites_map, allowed_variant_types=set([]), allowed_genes=set([]), min_freq=0, min_change=0.8):

    total_genes = set(passed_sites_map.keys())

    if len(allowed_genes)==0:
        allowed_genes = set(passed_sites_map.keys())
    
    allowed_genes = (allowed_genes & total_genes)     
    
    if len(allowed_variant_types)==0:
        allowed_variant_types = set(['1D','2D','3D','4D'])    
                    
    fixation_matrix = numpy.zeros_like(passed_sites_map.values()[0].values()[0]['sites'])*1.0  
    passed_sites = numpy.zeros_like(fixation_matrix)*1.0
    
    for gene_name in allowed_genes:
        
        for variant_type in passed_sites_map[gene_name].keys():
             
            if variant_type not in allowed_variant_types:
                continue
        
            passed_sites += passed_sites_map[gene_name][variant_type]['sites']
   
            allele_counts = allele_counts_map[gene_name][variant_type]['alleles']                        
            if len(allele_counts)==0:
                continue
            

            depths = allele_counts.sum(axis=2)
            alt_freqs = allele_counts[:,:,0]/(depths+(depths==0))
            alt_freqs[alt_freqs<min_freq] = 0.0
            alt_freqs[alt_freqs>=(1-min_freq)] = 1.0
            passed_depths = (depths>0)[:,:,None]*(depths>0)[:,None,:]
    
            delta_freq = numpy.fabs(alt_freqs[:,:,None]-alt_freqs[:,None,:])
            delta_freq[passed_depths==0] = 0
            delta_freq[delta_freq<min_change] = 0
        
            fixation_matrix += delta_freq.sum(axis=0)
        
    return fixation_matrix, passed_sites  

####
#
# Calculates the number of within-patient polymorphism differences between
# two samples. (e.g. something that is fixed in one timepoint and polymorphic
# in another. 
#
####
def calculate_new_snp_matrix(allele_counts_map, passed_sites_map, allowed_variant_types=set([]), allowed_genes=set([]), min_freq=0.05, max_freq=0.2):

    total_genes = set(passed_sites_map.keys())

    if len(allowed_genes)==0:
        allowed_genes = set(passed_sites_map.keys())
    
    allowed_genes = (allowed_genes & total_genes)     
    
    if len(allowed_variant_types)==0:
        allowed_variant_types = set(['1D','2D','3D','4D'])    
                    
    new_snp_matrix = numpy.zeros_like(passed_sites_map.values()[0].values()[0]['sites'])*1.0  
    passed_sites = numpy.zeros_like(new_snp_matrix)*1.0
    
    for gene_name in allowed_genes:
        
        for variant_type in passed_sites_map[gene_name].keys():
             
            if variant_type not in allowed_variant_types:
                continue
        
            passed_sites += passed_sites_map[gene_name][variant_type]['sites']
   
            allele_counts = allele_counts_map[gene_name][variant_type]['alleles']                        
            if len(allele_counts)==0:
                continue
            

            depths = allele_counts.sum(axis=2)
            freqs = allele_counts[:,:,0]/(depths+(depths==0))
            # turn into minor allele frequencies
            mafs = numpy.fmin(freqs,1-freqs)
            
            # Turn
            
            new_snps_1 = (mafs[:,:,None]<min_freq)*(mafs[:,None,:]>max_freq)
            new_snps_2 = (mafs[:,:,None]>max_freq)*(mafs[:,None,:]<min_freq)
            total_new_snps = new_snps_1+new_snps_2
             
            passed_depths = (depths>0)[:,:,None]*(depths>0)[:,None,:]
    
            total_new_snps[passed_depths==0] = 0
            
            new_snp_matrix += total_new_snps.sum(axis=0)
        
    return new_snp_matrix, passed_sites  


   
def calculate_pi_matrix(allele_counts_map, passed_sites_map, variant_type='4D', allowed_genes=None):

    if allowed_genes == None:
        allowed_genes = set(passed_sites_map.keys())
        
    pi_matrix = numpy.zeros_like(passed_sites_map[passed_sites_map.keys()[0]][variant_type]['sites'])*1.0
    avg_pi_matrix = numpy.zeros_like(pi_matrix)
    passed_sites = numpy.zeros_like(pi_matrix)
    
    for gene_name in allowed_genes:
        
        if gene_name in passed_sites_map.keys():
            #print passed_sites_map[gene_name][variant_type].shape, passed_sites.shape
            #print gene_name, variant_type
        
            passed_sites += passed_sites_map[gene_name][variant_type]['sites']
           
            allele_counts = allele_counts_map[gene_name][variant_type]['alleles']

            if len(allele_counts)==0:
                continue
         

            depths = allele_counts.sum(axis=2)
            freqs = allele_counts/(depths+(depths<0.1))[:,:,None]
            self_freqs = (allele_counts-1)/(depths-1+2*(depths<1.1))[:,:,None]
            self_pis = ((depths>0)-(freqs*self_freqs).sum(axis=2))
             
            I,J = depths.shape
    
            # pi between sample j and sample l
            gene_pi_matrix = numpy.einsum('ij,il',(depths>0)*1.0,(depths>0)*1.0)-numpy.einsum('ijk,ilk',freqs,freqs)
    
            # average of pi within sample j and within sample i
            gene_avg_pi_matrix = (numpy.einsum('ij,il',self_pis,(depths>0)*1.0)+numpy.einsum('ij,il',(depths>0)*1.0,self_pis))/2
    
            diagonal_idxs = numpy.diag_indices(J)
            gene_pi_matrix[diagonal_idxs] = gene_avg_pi_matrix[diagonal_idxs]
    
            pi_matrix += gene_pi_matrix
            avg_pi_matrix += gene_avg_pi_matrix
     
    # We used to normalize here    
    #pi_matrix = pi_matrix /(passed_sites+(passed_sites==0))
    #avg_pi_matrix = avg_pi_matrix/(passed_sites+(passed_sites==0))
    # Now we return passed sites
    
    return pi_matrix, avg_pi_matrix, passed_sites



    
def phylip_distance_matrix_str(matrix, samples):
    
    lines = [str(len(samples))]
    for i in xrange(0,len(samples)):
        lines.append( "\t".join([samples[i]]+["%g" % x for x in matrix[i,:]]))
    
    return "\n".join(lines)
    
import numpy
from scipy.special import gammaln as loggamma

def fold_sfs(fs):
    n = len(fs)+1
    folded_fs = (fs + fs[::-1])[0:(n-1)/2]
    if (n-1) % 2 != 0:
        folded_fs[-1] *= 0.5
    return folded_fs


def estimate_sfs_naive_binning(allele_counts, target_depth=10):

    depths = allele_counts.sum(axis=1)
    
    allele_counts = allele_counts[depths>0]
    depths = depths[depths>0]
    
    freqs = allele_counts[:,0]/depths
    
    bins = (numpy.arange(0,target_depth+2)-0.5)/target_depth
    
    counts,dummy = numpy.histogram(freqs,bins)
    
    return counts

def estimate_sfs_downsampling(allele_counts, target_depth=10):
    
    depths = allele_counts.sum(axis=1)
    
    allele_counts = allele_counts[depths>0]
    depths = depths[depths>0]
    
    Dmin = min([depths.min(),target_depth]) # this is what we have to downsample to
    # if you don't like it, send us an allele_counts matrix
    # that has been thresholded to a higher min value
    
    count_density = numpy.zeros(Dmin+1)*1.0

    
    A = numpy.outer(allele_counts[:,0], numpy.ones(Dmin+1))
    D = numpy.outer(depths, numpy.ones(Dmin+1))
    ks = numpy.outer(numpy.ones_like(depths), numpy.arange(0,Dmin+1))
    
    count_density = numpy.exp(loggamma(A+1)-loggamma(A-ks+1)-loggamma(ks+1) + loggamma(D-A+1)-loggamma(D-A-(Dmin-ks)+1)-loggamma(Dmin-ks+1) + loggamma(D-Dmin+1) + loggamma(Dmin+1) - loggamma(D+1)).sum(axis=0)
    
    return count_density
    
    

# Calculate polarized SNP changes from i to j that exceed threshold 
# Returns list of differences. Each difference is a tuple of form 
#
# (gene_name, (contig, location), (alt_i, depth_i), (alt_j, depth_j))
#
def calculate_snp_differences_between(i,j,allele_counts_map, passed_sites_map, allowed_variant_types=set([]), allowed_genes=set([]), min_freq=0, min_change=0.8):

    if len(allowed_genes)==0:
        allowed_genes = set(passed_sites_map.keys())
        
    if len(allowed_variant_types)==0:
        allowed_variant_types = set(['1D','2D','3D','4D'])    
    
    snp_changes = []
        
    for gene_name in allowed_genes:
        
        if gene_name not in allele_counts_map.keys():
            continue
            
        for variant_type in allele_counts_map[gene_name].keys():
            
            if variant_type not in allowed_variant_types:
                continue

            allele_counts = allele_counts_map[gene_name][variant_type]['alleles']
                        
            if len(allele_counts)==0:
                continue

            allele_counts = allele_counts[:,[i,j],:]
            depths = allele_counts.sum(axis=2)
            alt_freqs = allele_counts[:,:,0]/(depths+(depths==0))
            alt_freqs[alt_freqs<min_freq] = 0.0
            alt_freqs[alt_freqs>=(1-min_freq)] = 1.0
            
            passed_depths = (depths>0)[:,:,None]*(depths>0)[:,None,:]
    
            passed_depths = (depths>0)[:,0]*(depths>0)[:,1]
            
            delta_freqs = numpy.fabs(alt_freqs[:,1]-alt_freqs[:,0])
            delta_freqs[passed_depths==0] = 0
            delta_freqs[delta_freqs<min_change] = 0
    
            changed_sites = numpy.nonzero(delta_freqs)[0]
            
            if len(changed_sites)>0:
                # some fixations!
                
                for idx in changed_sites:
                    snp_changes.append((gene_name, allele_counts_map[gene_name][variant_type]['locations'][idx], (allele_counts[idx,0], depths[idx,0]), (allele_counts[idx,1],depths[idx,1]) ))
                        
    return snp_changes

# min_d = pick only a single sample per cluster with distance below this value
# max_d = cut tree at this distance
def cluster_samples(distance_matrix, min_d=0, max_d=1e09):
 
    # calculate compressed distance matrix suitable for agglomerative clustering
    Y = []
    for i in xrange(0,distance_matrix.shape[0]):
        for j in xrange(i+1,distance_matrix.shape[1]):
            Y.append(distance_matrix[i,j]) 
    Y = numpy.array(Y) 
     
    Z = linkage(Y, method='average')        
     
    c, coph_dists = cophenet(Z, Y)
     
    cluster_assignments = fcluster(Z, max_d, criterion='distance')
    subcluster_assignments = fcluster(Z, min_d, criterion='distance')
     
    cluster_labels = list(set(cluster_assignments))
     
    cluster_idx_map = {cluster_label: [] for cluster_label in cluster_labels}
    subcluster_map = {cluster_label: set([]) for cluster_label in cluster_labels}
    for i in xrange(0,len(cluster_assignments)):
        if subcluster_assignments[i] not in subcluster_map[cluster_assignments[i]]:
            cluster_idx_map[cluster_assignments[i]].append(i)
            subcluster_map[cluster_assignments[i]].add(subcluster_assignments[i])
         
    cluster_idxss = [set(cluster_idx_map[cluster_label]) for cluster_label in cluster_labels]
    cluster_sizes = [len(cluster_idxs) for cluster_idxs in cluster_idxss]
     
    # only return ones with more than one individual
    final_clusters = []
    final_cluster_sizes = []
     
    all_unique_idxs = set([])
    for cluster_idxs in cluster_idxss:
        all_unique_idxs.update(cluster_idxs)
     
    for cluster_idx_set in cluster_idxss:
         
        if len(cluster_idx_set)>1:
         
            cluster_idxs = numpy.array([(i in cluster_idx_set) for i in xrange(0,len(cluster_assignments))])
            anticluster_idxs = numpy.array([((i not in cluster_idx_set) and (i in all_unique_idxs)) for i in xrange(0,len(cluster_assignments))])  
         
            final_clusters.append((cluster_idxs, anticluster_idxs))
            final_cluster_sizes.append((cluster_idxs*1.0).sum())
             
     
    final_cluster_idxs = [i for i in xrange(0,len(final_cluster_sizes))]
         
    final_cluster_sizes, final_cluster_idxs = zip(*sorted(zip(final_cluster_sizes, final_cluster_idxs),reverse=True))
     
    sorted_final_clusters = [final_clusters[idx] for idx in final_cluster_idxs]
         
    return sorted_final_clusters
     
 
def calculate_phylogenetic_consistency(allele_counts_map, passed_sites_map, clusters, allowed_variant_types=set([]), allowed_genes=set([]), min_freq=0, min_change=0.8):
 
    total_genes = set(passed_sites_map.keys())
 
    if len(allowed_genes)==0:
        allowed_genes = set(passed_sites_map.keys())
     
    allowed_genes = (allowed_genes & total_genes)     
     
    if len(allowed_variant_types)==0:
        allowed_variant_types = set(['1D','2D','3D','4D'])    
                     
    total_polymorphic_sites = 0
    total_inconsistent_sites = 0
     
    for gene_name in allowed_genes:
         
        for variant_type in passed_sites_map[gene_name].keys():
              
            if variant_type not in allowed_variant_types:
                continue
         
            allele_counts = allele_counts_map[gene_name][variant_type]['alleles']                        
            if len(allele_counts)==0:
                continue
             
            # good to go, let's get calculating!
            depths = allele_counts.sum(axis=2)
            freqs = allele_counts[:,:,0]*1.0/(depths+(depths==0))
            passed_sites_matrix = (depths>0)
            # consensus approximation
            genotype_matrix = numpy.around(freqs)
     
            for cluster_idxs, anticluster_idxs in clusters:
             
                #print cluster_idxs.shape, anticluster_idxs.shape, genotype_matrix.shape, passed_sites_matrix.shape
             
                cluster_prevalence = (genotype_matrix[:,cluster_idxs]*passed_sites_matrix[:,cluster_idxs]).sum(axis=1)
                cluster_min_prevalence = 0.5
                cluster_max_prevalence = (passed_sites_matrix[:,cluster_idxs]).sum(axis=1)-0.5
             
                anticluster_prevalence = (genotype_matrix[:,anticluster_idxs]*passed_sites_matrix[:,anticluster_idxs]).sum(axis=1)
                anticluster_min_prevalence = 0.5
                anticluster_max_prevalence = (passed_sites_matrix[:,anticluster_idxs]).sum(axis=1) - 0.5
             
                # Those that are polymorphic in the clade!
                polymorphic_sites = (cluster_prevalence>cluster_min_prevalence)*(cluster_prevalence<cluster_max_prevalence)
                 
                # Those that are also polymorphic in the remaining population!
                inconsistent_sites = polymorphic_sites*(anticluster_prevalence>anticluster_min_prevalence)*(anticluster_prevalence<anticluster_max_prevalence)
             
                num_polymorphic_sites = polymorphic_sites.sum()
                num_inconsistent_sites = inconsistent_sites.sum()
             
                total_polymorphic_sites += num_polymorphic_sites
                total_inconsistent_sites += num_inconsistent_sites
             
                if num_inconsistent_sites > 0:
                    print cluster_prevalence[inconsistent_sites], cluster_max_prevalence[inconsistent_sites]
                    print anticluster_prevalence[inconsistent_sites], anticluster_max_prevalence[inconsistent_sites]
                    print (cluster_idxs*anticluster_idxs).sum()
             
         
    return total_inconsistent_sites, total_polymorphic_sites
 
