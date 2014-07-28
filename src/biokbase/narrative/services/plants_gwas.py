"""
Plants GWAS service.
"""

__author__ = 'Dan Gunter <dkgunter@lbl.gov>'
__date__ = '12/12/13'

## Imports

# Stdlib
import json
# Third party
# Service framework
from biokbase.narrative.common.service import init_service, method, finalize_service
# Other KBase
from biokbase.GWAS.Client import GWAS
from biokbase.narrative.common.util import AweJob, Workspace2
from biokbase.KBaseNetworksService2.Client import KBaseNetworks
import sys

## Exceptions


class GWASException(Exception):
    pass

## Globals

VERSION = (0, 0, 1)
NAME = "GWAS Services"

GENE_NETWORK_OBJECT_TYPE = "KBaseGwasData.GwasGeneList"


class URLS:
    _host = '140.221.84.248'
    main = "http://140.221.84.236:8000/node"
    shock = "http://140.221.84.236:8000"
    awe = "http://140.221.85.182:7080"
    #workspace = "https://kbase.us/services/ws/"
    ids = "http://kbase.us/services/idserver"
    cdmi = "http://kbase.us/services/cdmi_api"
    ontology = "http://kbase.us/services/ontology_service"
    gwas = "http://140.221.85.182:7086"
    gwas1 = "http://140.221.85.95:7086"
    ujs = "http://140.221.85.171:7083"
    #networks = "http://kbase.us/services/networks"
    networks = "http://140.221.85.172:7064/KBaseNetworksRPC/networks"

AweJob.URL = URLS.awe

# Initialize
init_service(name=NAME, desc="Plants GWAS service", version=VERSION)


def _output_object(name):
    """Format an object ID as JSON output, for returning from a narr. function.
    """
    return json.dumps({'output': name})


def _workspace_output(wsid):
    return json.dumps({'values': [["Workspace object", wsid]]})





@method(name="Prepare Variation data for GWAS")
def maf(meth, maf=0.05, variation=None, out=None, comment=None):
    """Perform filtering on Minor allele frequency (MAF).
    Minor allele frequency (MAF) refers to the frequency at which the least common
    <a href="http://en.wikipedia.org/wiki/Allele">allele</a> occurs in a given population.

    :param maf: Minor allele frequency
    :type maf: kbtypes.Numeric
    :param variation: Population variation object
    :type variation: kbtypes.KBaseGwasData.GwasPopulationVariation
    :param out: Population variation, filtered 
    :type out: kbtypes.KBaseGwasData.GwasPopulationVariation
    :param comment: Comment
    :type comment: kbtypes.Unicode
    :return: Workspace ID of filtered data
    :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    meth.stages = 3

    meth.advance("init GWAS service")
    gc = GWAS(URLS.gwas, token=meth.token)

    argsx = {"ws_id" : meth.workspace_id, "inobj_id" : variation, "outobj_id" : out, "minor_allele_frequency" : maf, "comment" : "comment"}
    meth.advance("submit job to filter VCF")
    try:
        jid = gc.prepare_variation(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))
    if not jid:
        raise GWASException(2, "submit job failed, no job id")

    AweJob.URL = URLS.awe
    AweJob(meth, started="run VCF", running="VCF").run(jid[0])
    return _workspace_output(out)


@method(name="Calculate Kinship matrix")
def gwas_run_kinship(meth,  filtered_variation=None, out=None, comment=None):
    """Computes the n by n kinship matrix for a set of n related subjects.
       The kinship matrix defines pairwise genetic relatedness among individuals and
       is estimated by using all genotyped markers. This requires the filtered SNPs as input.

    :param filtered_variation: Population variation, filtered
    :type filtered_variation: kbtypes.KBaseGwasData.GwasPopulationVariation
    :param out: Computed Kinship matrix
    :type out: kbtypes.KBaseGwasData.GwasPopulationKinship
    :param comment: Comment
    :type comment: kbtypes.Unicode
    :return: New workspace object
    :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    meth.stages = 3

    meth.advance("init GWAS service")
    gc = GWAS(URLS.gwas, token=meth.token)

    argsx = {"ws_id" : meth.workspace_id, "inobj_id" : filtered_variation, "outobj_id" : out,  "comment" : "comment"}
    meth.advance("submit job to select_random_snps")
    try:
        jid = gc.calculate_kinship_matrix(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))
    if not jid:
        raise GWASException(2, "submit job failed, no job id")

    AweJob.URL = URLS.awe
    AweJob(meth, started="Calculate Kinship matrix", running="Kinship matrix").run(jid[0])
    return _workspace_output(out)


@method(name="Run GWAS analysis")
def gwas_run_gwas2(meth,  genotype=None,  kinship_matrix=None, traits=None,  out=None):
    """Computes association between each SNP and a trait of interest that has been scored
    across a large number of individuals. This method takes Filtered SNP object,
    kinship matrix, trait object as input and computes association.

   :param genotype: Population variation object
   :type genotype: kbtypes.KBaseGwasData.GwasPopulationVariation
   :param kinship_matrix: Kinship matrix object id
   :type kinship_matrix: kbtypes.KBaseGwasData.GwasPopulationKinship
   :param traits: Trait object id
   :type traits: kbtypes.KBaseGwasData.GwasPopulationTrait
   :param out: Output
   :type out: kbtypes.KBaseGwasData.GwasTopVariations
   :return: New workspace object
   :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    meth.stages = 3

    meth.advance("init GWAS service")
    gc = GWAS(URLS.gwas, token=meth.token)

    argsx = {"ws_id" : meth.workspace_id, "variation_id" : genotype, "trait_id" : traits,  "kinship_id": kinship_matrix, "out_id" : out, "comment" : "comment"}
    meth.advance("submit job to run GWAS analysis")
    try:
        jid = gc.run_gwas(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))
    if not jid:
        raise GWASException(2, "submit job failed, no job id")

    AweJob.URL = URLS.awe
    AweJob(meth, started="GWAS analysis using emma", running="GWAS analysis using emma").run(jid[0])
    return _workspace_output(out)


@method(name="Trait Manhattan Plot")
def trait_manhattan_plot(meth, workspaceID=None, gwas_result=None):
    """Widget to visualize top SNPs related to a trait on the manhattan plot.
    On the X-axis of the plot are all contigs, and
    on the Y-axis is -log10(pvalue) of SNPs-association for the trait.

    :param workspaceID: workspaceID (use current if empty)
    :type workspaceID: kbtypes.Unicode
    :param gwas_result: GWAS analysis (MLM) result
    :type gwas_result: kbtypes.KBaseGwasData.GwasTopVariations
    :return: Workspace objectID of gwas results
    :rtype: kbtypes.Unicode
    :output_widget: Manhattan
    """
    meth.stages = 1
    if not workspaceID:
        workspaceID = meth.workspace_id
    meth.advance("Manhattan plot")
    token = meth.token
    return json.dumps({'token': token, 'workspaceID': workspaceID, 'gwasObjectID': gwas_result})


@method(name="GWAS Variation To Genes")
def gwas_variation_to_genes(meth, workspaceID=None, gwasObjectID=None, num2snps=None, pmin=None, distance=None, out=None):
    """This method takes the top SNPs obtained after GWAS analysis as input
    (TopVariations) object, -log (pvalue) cutoff and a distance parameter as input.
    For each significant SNP that passes the p-value cutoff, genes are searched in the
    window specified by the distance parameter.

    :param workspaceID: Workspace (use current if empty)
    :type workspaceID: kbtypes.Unicode
    :param gwasObjectID: GWAS analysis MLM result object
    :type gwasObjectID: kbtypes.KBaseGwasData.GwasTopVariations
    :param num2snps: Number to snps
    :type num2snps: kbtypes.Numeric
    :default num2snps: 100
    :param pmin: Minimum pvalue (-log10)
    :type pmin: kbtypes.Numeric
    :default pmin: 4
    :param distance: Distance in bp around SNP to look for genes
    :type distance: kbtypes.Numeric
    :default distance: 10000
    :param out: Output
    :type out: kbtypes.KBaseGwasData.GwasGeneList
    :return: Workspace objectID of gwas results
    :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    meth.stages = 3

    if not workspaceID:
        workspaceID = meth.workspace_id

    meth.advance("init GWAS service")
    gc = GWAS(URLS.gwas, token=meth.token)
    meth.advance("Running Variations to Genes")
    argsx = {"ws_id" : meth.workspace_id, "variation_id" : gwasObjectID,  "out_id": out, "num2snps" : num2snps, "pmin": pmin, "distance" : distance, "comment" : "comment"}
    try:
        gl_oid = gc.variations_to_genes(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))
    #if not gl_oid: # it may return empty string based on current script
    #    raise GWASException(2, "submit job failed, no job id")

    meth.advance("Returning object")
    #return _workspace_output("Genelist.{}-{}".format(gwasObjectID, pmin))
    return _workspace_output(out)


GENE_TABLE_OBJECT_TYPE = "KBaseGwasData.GwasGeneList"


@method(name="Gene table")
def gene_table(meth, obj_id=None):
    """This method displays a gene list
    along with functional annotation in a table.

    :param obj_id: Gene List workspace object identifier.
    :type obj_id: kbtypes.KBaseGwasData.GwasGeneList
    :return: Rows for display
    :rtype: kbtypes.Unicode
    :output_widget: GeneTableWidget
    """
    # :param workspace_id: Workspace name (if empty, defaults to current workspace)
    # :type workspace_id: kbtypes.Unicode
    meth.stages = 1
    meth.advance("Retrieve genes from workspace")
    # if not workspace_id:
    #     meth.debug("Workspace ID is empty, setting to current ({})".format(meth.workspace_id))
    #     workspace_id = meth.workspace_id
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    raw_data = ws.get(obj_id)
    genes = raw_data['genes']
    header = ["KBase Chromosome ID", "Source gene ID", "KBase Gene ID", "Gene function", "Source Chromosome ID"]
    data = {'table': [header] + genes}
    return json.dumps(data)

@method(name="GeneList to Networks")
def gene_network2ws(meth, obj_id=None, out_id=None):
    """This method displays a gene list
    along with functional annotation in a table.

    :param obj_id: Gene List workspace object identifier.
    :type obj_id: kbtypes.KBaseGwasData.GwasGeneList
    :param out_id: Output Networks object identifier
    :type out_id: kbtypes.KBaseNetworks.Network
    :return: New workspace object
    :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    # :param workspace_id: Workspace name (if empty, defaults to current workspace)
    # :type workspace_id: kbtypes.Unicode
    meth.stages = 2
    meth.advance("Retrieve genes from workspace")
    # if not workspace_id:
    #     meth.debug("Workspace ID is empty, setting to current ({})".format(meth.workspace_id))
    #     workspace_id = meth.workspace_id
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    nc = KBaseNetworks(URLS.networks)

    raw_data = ws.get(obj_id)
    
    meth.advance("Construct networks")
    ds = set()
    #tx = set()

    gl = [ gr[2] for gr in raw_data['genes']]
    for gene in gl:
    #    rst= re.search('\A(kb\|g\.\d+)', gene)
    #    tx.add(rst.group(1))
        lds = nc.entity2datasets(gene)
        llds = [ i['id'] for i in lds]
        ds.update((llds))
    #for t in tx:
    #    lds = nc.taxon2datasets(t)
    #    llds = [ i['id'] for i in lds]
    #    ds.update((llds))
        
    # TODO: include cluster node later 
    #cnet = nc.build_first_neighbor_network(list(ds),gl,['GENE_CLUSTER'])
    #agl = [i['entity_id'] for i in cnet['nodes']]
    #gl = gl.union(agl)
    #net = nc.build_internal_network(list(ds),list(gl),['GENE_GENE','GENE_CLUSTER'])
    net = nc.build_internal_network(list(ds),gl,['GENE_GENE'])
    ws.save_objects({'workspace' : meth.workspace_id, 'objects' : [{'type' : 'KBaseNetworks.Network', 'data' : net, 'name' : out_id, 'meta' : {'source' : obj_id}}]})

    #sys.stderr.write('@ ' + list(gl)[0] + '-----\n')
    #sys.stderr.write('@ ' + list(ds)[0] + '+++++\n')
    #sys.stderr.flush()
    
    return _workspace_output(out_id)


@method(name="Gene network")
def gene_network(meth, gene_list=None, external_ids=None):
    """This method searches KBase indexed co-expression networks where
        genes from the gene_list are present and displays internal networks formed by these genes in an interactive visualization.
        
        :param gene_list: GWAS Gene list
        :type gene_list: kbtypes.KBaseGwasData.GwasGeneList
        :param external_ids: Space delimited list of external IDs (optional. Use this or workspace id)
        :type external_ids: kbtypes.Unicode
        :return: Rows for display
        :rtype: kbtypes.Unicode
        :output_widget: kbasePlantsNetworkNarrative
        """
    #:param workspace_id: Workspace name (use current if empty)
    #:type workspace_id: kbtypes.Unicode
    meth.stages = 1
    # if not workspace_id:
    #     meth.debug("Workspace ID is empty, setting to current ({})".format(meth.workspace_id))
    #     workspace_id = meth.workspace_id
    meth.advance("Retrieve gene from workspace")
    if gene_list:
        ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
        raw_data = ws.get(gene_list)
    else:
        raw_data = {}
    data = {'gwas': raw_data, 'external_ids' : external_ids}
    return json.dumps(data)



# Finalize (registers service)
finalize_service()
