"""
Plants GWAS service.
"""

__author__ = 'Dan Gunter <dkgunter@lbl.gov>'
__date__ = '12/12/13'

## Imports

# Stdlib
import json
from string import Template
from operator import itemgetter
# Third party
# Service framework
from biokbase.narrative.common.service import init_service, method, finalize_service
# Other KBase
from biokbase.GWAS.Client import GWAS
from biokbase.narrative.common.util import AweJob, Workspace2
from biokbase.KBaseNetworksService2.Client import KBaseNetworks
from biokbase.cdmi.client import CDMI_API,CDMI_EntityAPI
from biokbase.IdMap.Client import IdMap
from biokbase.OntologyService.Client import Ontology
import sys
import os

## Exceptions


class GWASException(Exception):
    pass

## Globals

VERSION = (0, 0, 1)
NAME = "GWAS Services"

GENE_NETWORK_OBJECT_TYPE = "KBaseGwasData.GwasGeneList"


class URLS:
    #awe = "http://140.221.85.182:7080"
    awe = "https://kbase.us/services/awe-api/"
    #workspace = "https://kbase.us/services/ws/"
    ids = "http://kbase.us/services/idserver"
    cdmi = "http://kbase.us/services/cdmi_api"
    #cdmi = "http://140.221.85.181:7032"
    ontology = "http://kbase.us/services/ontology_service"
    #gwas = "http://140.221.85.182:7086"
    gwas = "https://kbase.us/services/GWAS"
    ujs = "https://kbase.us/services/userandjobstate"
    networks = "http://kbase.us/services/networks"
    #networks = "http://140.221.85.172:7064/KBaseNetworksRPC/networks"
    idmap = "http://kbase.us/services/id_map"
    #idmap = "http://140.221.85.181:7111"

AweJob.URL = URLS.awe

# Initialize
init_service(name=NAME, desc="Plants GWAS service", version=VERSION)


def _output_object(name):
    """Format an object ID as JSON output, for returning from a narr. function.
    """
    return json.dumps({'output': name})


def _workspace_output(wsid):
    return json.dumps({'values': [["Workspace object", wsid]]})

class Node:
    nodes = []
    edges = []
    ugids = {}
    igids = {}
    gid2nt = {}
    clst2genes = {}

    def __init__(self, unodes = [], uedges=[]):
      self._register_nodes(unodes)
      self._register_edges(uedges)

    def get_node_id(self, node, nt = "GENE"):
      if not node in self.ugids.keys() :
          #print node + ":" + nt
          self.ugids[node] = len(self.ugids)
          self.nodes.append( {
            'entity_id' : node,
            'name' : node,
            'user_annotations' : {},
            'type' : nt,
            'id' : 'kb|netnode.' + `self.ugids[node]`,
            'properties' : {}
          } )
          self.igids['kb|netnode.' + `self.ugids[node]`] = node
          self.gid2nt[node] = nt
      return "kb|netnode." + `self.ugids[node]`

    def get_node_id(self, node, eid, nt = "GENE"):
      if not node in self.ugids.keys() :
          #print node + ":" + nt
          self.ugids[node] = len(self.ugids)
          self.nodes.append( {
            'entity_id' : node,
            'name' : eid,
            'user_annotations' : {},
            'type' : nt,
            'id' : 'kb|netnode.' + `self.ugids[node]`,
            'properties' : {}
          } )
          self.igids['kb|netnode.' + `self.ugids[node]`] = node
          self.gid2nt[node] = nt
      return "kb|netnode." + `self.ugids[node]`

    def add_edge(self, strength, ds_id, node1, nt1, node2, nt2, confidence):
      #print node1 + "<->" + node2
      self.edges.append( {
          'name' : 'interacting gene pair',
          'properties' : {},
          'strength' : float(strength),
          'dataset_id' : ds_id,
          'directed' : 'false',
          'user_annotations' : {},
          'id' : 'kb|netedge.'+`len(self.edges)`,
          'node_id1' : self.get_node_id(node1, nt1),
          'node_id2' : self.get_node_id(node2, nt2),
          'confidence' : float(confidence)
      })
      if(nt1 == 'CLUSTER'):
        if not node1 in self.clstr2genes.keys() : self.clst2genes[node1] = {}
        if(nt2 == 'GENE'):
          self.clst2gene[node1][node2] = 1
      else:
        if(nt2 == 'CLUSTER'):
          if not node2 in self.clst2genes.keys() : self.clst2genes[node2] = {}
          self.clst2genes[node2][node1] = 1

    def add_edge(self, strength, ds_id, node1, nt1, node2, nt2, confidence, eid1, eid2):
      #print node1 + "<->" + node2
      self.edges.append( {
          'name' : 'interacting gene pair',
          'properties' : {},
          'strength' : float(strength),
          'dataset_id' : ds_id,
          'directed' : 'false',
          'user_annotations' : {},
          'id' : 'kb|netedge.'+`len(self.edges)`,
          'node_id1' : self.get_node_id(node1, eid1, nt1),
          'node_id2' : self.get_node_id(node2, eid2, nt2),
          'confidence' : float(confidence)
      })
      if(nt1 == 'CLUSTER'):
        if not node1 in self.clstr2genes.keys() : self.clst2genes[node1] = {}
        if(nt2 == 'GENE'):
          self.clst2gene[node1][node2] = 1
      else:
        if(nt2 == 'CLUSTER'):
          if not node2 in self.clst2genes.keys() : self.clst2genes[node2] = {}
          self.clst2genes[node2][node1] = 1

    def _register_nodes(self, unodes):
      self.nodes = unodes
      self.ugids = {}
      for node in self.nodes:
        nnid = node['id']
        nnid = nnid.replace("kb|netnode.","");
        self.ugids[node['entity_id']] = nnid
        self.igids[node['id']] = node['entity_id']
        self.gid2nt[node['entity_id']] = node['type']

    def _register_edges(self, uedges):
      self.edges = uedges
      for edge in self.edges:
        node1 = self.igids[edge['node_id1']];
        nt1  = self.gid2nt[node1];
        node2 = self.igids[edge['node_id2']];
        nt2  = self.gid2nt[node2];
        if(nt1 == 'CLUSTER'):
          if not node1 in self.clstr2genes.keys() : self.clst2genes[node1] = {}
          if(nt2 == 'GENE'):
            self.clst2genes[node1][node2] = 1
        else:
          if(nt2 == 'CLUSTER'):
            if not node2 in self.clst2genes.keys() : self.clst2genes[node2] = {}
            self.clst2genes[node2][node1] = 1


    def get_gene_list(self, cnode):
      if(cnode in self.clst2genes.keys()) : return self.clst2genes[cnode].keys()
      return []



def ids2cds(ql):
    cdmic = CDMI_API(URLS.cdmi)
    idm = IdMap(URLS.idmap)

    gl = set()
    rd = {}
    eids = []
    lids = set()
    mids = set()
    for gid in ql:
      rd[gid] = gid
      if 'kb|g.' in gid:
        if 'locus' in gid:
          lids.add(gid)
        elif 'mRNA' in gid:
          mids.add(gid)
      else:
        eids.append(gid)

    sid2fids = cdmic.source_ids_to_fids(eids)
    for sid in sid2fids:
      for fid in sid2fids[sid]:
        rd[sid] = fid
        if 'locus' in fid:
          lids.add(fid)
        elif 'mRNA' in fid:
          mids.add(fid)
    lidmap = ()
    if len(lids) > 0: lidmap = idm.longest_cds_from_locus(list(lids))
    for lid in lidmap:
      for k in lidmap[lid]:
        gl.add(k)
    midl = list(mids)
    midmap = ()
    if len(mids) > 0: lidmap = idm.longest_cds_from_mrna(list(mids))
    for lid in midmap:
      for k in midmap[lid]:
        gl.add(k)

    for gid in ql:
      if 'kb|g.' in gid:
        if 'locus' in gid:
          for k in lidmap[gid]:
            rd[gid] = k
        elif 'mRNA' in gid:
          for k in midmap[gid]:
            rd[gid] = k
      else:
        if 'locus' in rd[gid]:
            for k in lidmap[rd[gid]]:
              rd[gid] = k
        elif 'mRNA' in rd[gid]:
            for k in midmap[rd[gid]]:
              rd[gid] = k
    return rd

def cds2locus(gids):
    cdmie = CDMI_EntityAPI(URLS.cdmi)
    mrnas_l = cdmie.get_relationship_IsEncompassedIn(gids, [], ['to_link'], [])
    mrnas = dict((i[1]['from_link'], i[1]['to_link']) for i in mrnas_l)
    locus_l = cdmie.get_relationship_IsEncompassedIn(mrnas.values(), [], ['to_link'], [])
    locus = dict((i[1]['from_link'], i[1]['to_link']) for i in locus_l)
    lgids = dict((i,locus[mrnas[i]]) for i in gids if i in mrnas and mrnas[i] in locus)
    return lgids

def genelist2fs(gl):
    qid2cds = ids2cds(gl)
    fs = {"description" : "Feature set generated by " + ",".join(gl),
          "elements" : {}
         }
    cdmie = CDMI_EntityAPI(URLS.cdmi)
    cdmic = CDMI_API(URLS.cdmi)
    cds_ids = qid2cds.values()
    cds2l = cds2locus(cds_ids);
    lfunc = cdmic.fids_to_functions(cds2l.values())

    fm = cdmie.get_entity_Feature(cds_ids,['feature_type', 'source_id', 'sequence_length', 'function', 'alias'])
    for i in cds_ids:
      if i in fm:
        if not fm[i]['function'] and cds2l[i] in lfunc:
          fm[i]['function'] = lfunc[cds2l[i]]
        fs['elements'][i] = {"data" : { 'type' : fm[i]['feature_type'], 'id' : i, 'dna_sequence_length' : int(fm[i]['sequence_length']), 'function' : fm[i]['function'], 'aliases' : fm[i]['alias']}}
    return fs

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
def gwas_variation_to_genes(meth, workspaceID=None, gwasObjectID=None, num2snps=None, pmin=None, distance=None, gl_out=None, fs_out=None):
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
    :param gl_out: Output GwasGeneLint workspace object name
    :type gl_out: kbtypes.KBaseGwasData.GwasGeneList
    :param fs_out: Output FeatureSet workspace object name
    :type fs_out: kbtypes.KBaseSearch.FeatureSet
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
    argsx = {"ws_id" : meth.workspace_id, "variation_id" : gwasObjectID,  "out_id": gl_out, "num2snps" : num2snps, "pmin": pmin, "distance" : distance, "comment" : "comment"}
    try:
        gl_oid = gc.variations_to_genes(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))

    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    raw_data = ws.get(gl_out)

    gl = [ gr[2] for gr in raw_data['genes']]
    fs = genelist2fs(gl)
    ws.save_objects({'workspace' : meth.workspace_id, 'objects' :[{'type' : 'KBaseSearch.FeatureSet', 'data' : fs, 'name' : fs_out, 'meta' : {'original' : gl_out}}]})

    meth.advance("Returning object")
    return json.dumps({'values': [
                                   ["Workspace GwasGeneList object", gl_out],
                                   ["Workspace FeatureSet object", fs_out]
                                 ]})


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
    meth.stages = 1
    meth.advance("Retrieve genes from workspace")
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
    meth.stages = 3
    meth.advance("init GWAS service")
    gc = GWAS(URLS.gwas, token=meth.token)

    meth.advance("Retrieve genes from workspace")
    # if not workspace_id:
    #     meth.debug("Workspace ID is empty, setting to current ({})".format(meth.workspace_id))
    #     workspace_id = meth.workspace_id
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)

    raw_data = ws.get(obj_id)


    gl = [ gr[2] for gr in raw_data['genes']]
    gl_str = ",".join(gl);

    meth.advance("Running GeneList to Networks")
    argsx = {"ws_id" : meth.workspace_id, "inobj_id" : gl_str,  "outobj_id": out_id}
    try:
        gl_oid = gc.genelist_to_networks(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))
    #if not gl_oid: # it may return empty string based on current script
    #    raise GWASException(2, "submit job failed, no job id")

    meth.advance("Returning object")
    return _workspace_output(out_id)

@method(name="FeatureSet table")
def featureset_table(meth, obj_id=None):
    """This method displays a FeatureSet gene list
    along with functional annotation in a table.

    :param obj_id: FeatureSet workspace object identifier.
    :type obj_id: kbtypes.KBaseSearch.FeatureSet
    :return: Rows for display
    :rtype: kbtypes.Unicode
    :output_widget: GeneTableWidget
    """
    meth.stages = 1
    meth.advance("Retrieve genes from workspace")
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    fs = ws.get(obj_id)
    if 'elements' not in fs: return {}
    header = ["KBase ID", "Source gene ID", "Gene function"]
    fs2 = genelist2fs(fs['elements'].keys())
    fields = []
    for gid in fs2['elements']:
      if 'data' in fs2['elements'][gid]:
        rec = fs2['elements'][gid]['data']
        sid = ""
        if rec['aliases'] and len(rec['aliases']) > 0: sid = rec['aliases'][0]
        fields.append([rec['id'], sid, rec['function']])

    data = {'table': [header] + fields}
    return json.dumps(data)

@method(name="User genelist to FeatureSet")
def genelist_to_featureset(meth, gene_ids=None, out_id=None):
    """This method converts user gene list to FeatureSet typed object.

    :param gene_ids: List of genes (comma separated)
    :type gene_ids: kbtypes.Unicode
    :param out_id: Output FeatureSet object identifier
    :type out_id: kbtypes.KBaseSearch.FeatureSet
    :return: New workspace object
    :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    meth.stages = 2
    meth.advance("Retrieve genes from Central Store")
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)

    gene_ids_ns = gene_ids.replace(" ","")
    fs = genelist2fs(gene_ids_ns.split(","))

    ws.save_objects({'workspace' : meth.workspace_id, 'objects' :[{'type' : 'KBaseSearch.FeatureSet', 'data' : fs, 'name' : out_id, 'meta' : {'original' : gene_ids}}]})

    meth.advance("Returning object")
    return json.dumps({'values': [
                                   ["Workspace object", out_id]
                                 ]})

@method(name="FeatureSet GO Analysis")
def featureset_go_anal(meth, feature_set_id=None, p_value=0.05, ec='IEA', domain='biological_process', out_id=None):
    """This method annotate GO terms and execute GO enrichment test

    :param feature_set_id: FeatureSet workspace object id
    :type feature_set_id: kbtypes.KBaseSearch.FeatureSet
    :param p_value: p-value cutoff
    :type p_value: kbtypes.Unicode
    :param ec: Evidence code list (comma separated, IEA,ISS,IDA,IEP,IPI,RCA ..)
    :type ec:kbtypes.Unicode
    :param domain: Domain list (comma separated, biological_process,molecular_function,cellular_component)
    :type domain: kbtypes.Unicode
    :param out_id: Output FeatureSet object identifier
    :type out_id: kbtypes.KBaseSearch.FeatureSet
    :return: New workspace object
    :rtype: kbtypes.Unicode
    :output_widget: GeneTableWidget
    """
    meth.stages = 4
    meth.advance("Prepare Enrichment Test")

    oc = Ontology(url=URLS.ontology)
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    fs = ws.get(feature_set_id)
    qid2cds = ids2cds(fs['elements'].keys())
    cds2l   = cds2locus(qid2cds.values())
    cdmic = CDMI_API(URLS.cdmi)
    lfunc = cdmic.fids_to_functions(cds2l.values())

    meth.advance("Annotate GO Term")
    ec = ec.replace(" ","")
    domain = domain.replace(" ","")
    ec_list = [ i for i in ec.split(',')]
    domain_list = [ i for i in domain.split(',')]
    ots = oc.get_goidlist(list(set(qid2cds.values())), domain_list, ec_list)
    go_key = lambda go, i, ext: "go.{}.{:d}.{}".format(go, i, ext)
    go2cds = {}
    for gid in fs['elements']:
      lid = qid2cds[gid]
      if 'data' in fs['elements'][gid]:
        if not fs['elements'][gid]['data']['function']: fs['elements'][gid]['data']['function'] = lfunc[cds2l[lid]]
      if 'metadata' not in fs['elements'][gid]: fs['elements'][gid]['metadata'] = {}
      if lid in ots:
          go_enr_list = []
          for lcnt, go in enumerate(ots[lid].keys()):
              if go not in go2cds: go2cds[go] = set()
              go2cds[go].add(lid)
              for i, goen in enumerate(ots[lid][go]):
                  for ext in "domain", "ec", "desc":
                      fs['elements'][gid]['metadata'][go_key(go, i, ext)] = goen[ext]
                      fs['elements'][gid]['metadata'][go_key(go, i, ext)] = goen[ext]

    meth.advance("Execute Enrichment Test")
    enr_list = oc.get_go_enrichment(list(set(qid2cds.values())), domain_list, ec_list, 'hypergeometric', 'GO')
    enr_list = sorted(enr_list, key=itemgetter('pvalue'), reverse=False)
    header = ["GO ID", "Description", "Domain", "p-value", "FeatureSet ID (# genes)"]
    fields = []
    objects = []
    go_enr_smry = ""
    for i in range(len(enr_list)):
      goen = enr_list[i]
      if goen['pvalue'] > float(p_value) : continue
      cfs = genelist2fs(list(go2cds[goen['goID']]))
      goid = goen['goID'].replace(":","")
      fields.append([goen['goID'], goen['goDesc'][0], goen['goDesc'][1], "{:12.10f}".format(goen['pvalue']), "{}_to_{} ({})".format(out_id, goid,len(go2cds[goen['goID']])) ])
      objects.append({'type' : 'KBaseSearch.FeatureSet', 'data' : cfs, 'name' : out_id + "_to_" + goid, 'meta' : {'original' : feature_set_id, 'domain' : domain, 'ec' : ec, 'GO_ID' :goen['goID']}})
      if i < 3 :
        go_enr_smry += goen['goID']+"(" + "{:6.4f}".format(goen['pvalue']) + ")" + goen['goDesc'][0] + "\n"
    go_enr_smry
    data = {'table': [header] + fields}


    meth.advance("Saving output to Workspace")
    objects.append({'type' : 'KBaseSearch.FeatureSet', 'data' : fs, 'name' : out_id, 'meta' : {'original' : feature_set_id, 'enr_summary' : go_enr_smry}})
    ws.save_objects({'workspace' : meth.workspace_id, 'objects' :objects})
    return json.dumps(data)

@method(name="FeatureSet to Networks")
def gene_network2ws(meth, feature_set_id=None, out_id=None):
    """ Query all available network data in KBase central store.

    :param feature_set_id: FeatureSet workspace object id
    :type feature_set_id: kbtypes.KBaseSearch.FeatureSet
    :param out_id: Output Networks object identifier
    :type out_id: kbtypes.KBaseNetworks.Network
    :return: New workspace object
    :rtype: kbtypes.Unicode
    :output_widget: ValueListWidget
    """
    meth.stages = 3
    meth.advance("init GWAS service")
    gc = GWAS(URLS.gwas, token=meth.token)

    meth.advance("Retrieve genes from workspace")
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    fs = ws.get(feature_set_id)
    qid2cds = ids2cds(fs['elements'].keys())

    gl_str = ",".join(list(set(qid2cds.values())));

    meth.advance("Running GeneList to Networks")
    argsx = {"ws_id" : meth.workspace_id, "inobj_id" : gl_str,  "outobj_id": out_id}
    try:
        gl_oid = gc.genelist_to_networks(argsx)
    except Exception as err:
        raise GWASException("submit job failed: {}".format(err))

    meth.advance("Returning object")

    return _workspace_output(out_id)

@method(name="FeatureSet Network Enrichment")
def featureset_net_enr(meth, feature_set_id=None, p_value=None, ref_wsid="KBasePublicNetwork", ref_network=None, out_id=None):
    """This method annotate GO terms and execute GO enrichment test

    :param feature_set_id: FeatureSet workspace object id
    :type feature_set_id: kbtypes.KBaseSearch.FeatureSet
    :param p_value: p-value cutoff
    :type p_value: kbtypes.Unicode
    :param ref_wsid: Reference Network workspace id (optional, default to current workspace)
    :type ref_wsid: kbtypes.Unicode
    :param ref_network: Reference Network object name
    :type ref_network:kbtypes.KBaseNetworks.Network
    :param out_id: Output FeatureSet object identifier
    :type out_id: kbtypes.KBaseSearch.FeatureSet
    :return: New workspace object
    :rtype: kbtypes.Unicode
    :output_widget: GeneTableWidget
    """
    meth.stages = 3
    meth.advance("Prepare Enrichment Test")

    oc = Ontology(url=URLS.ontology)
    ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
    fs = ws.get(feature_set_id)
    if  not ref_wsid : ref_wsid = meth.workspace_id
    ws2 = Workspace2(token=meth.token, wsid=ref_wsid)
    net = ws2.get(ref_network)

    # checking user input
    if 'edges' not in net or 'nodes' not in net or 'elements' not in fs: return "{}"

    qid2cds = ids2cds(fs['elements'].keys())
    # parse networks object
    nc = Node(net['nodes'],net['edges']);

    meth.advance("Execute Enrichment Test")
    qcdss = set(qid2cds.values())
    enr_dict = oc.association_test(list(qcdss), ref_wsid, ref_network, '', 'hypergeometric', 'none', p_value)
    enr_list = sorted([(value,key) for (key,value) in enr_dict.items()])


    nid2name = {}
    for ne in net['nodes']:
      nid2name[ne['entity_id']] = ne['name']

    pwy_enr_smry = ""
    header = ["Pathway ID", "Name", "p-value", "FeatureSet ID (# genes)"]
    fields = []
    objects = []
    for i in range(len(enr_list)):
      pwy_en = enr_list[i]
      if float(pwy_en[0]) > float(p_value) : continue
      cgenes = set(nc.get_gene_list(pwy_en[1]))
      cgenes = list(cgenes.intersection(qcdss))
      cfs = genelist2fs(cgenes)
      fields.append([pwy_en[1], nid2name[pwy_en[1]], "{:12.10f}".format(float(pwy_en[0])), out_id + "_to_" + pwy_en[1] + "({})".format(len(cgenes))])
      objects.append({'type' : 'KBaseSearch.FeatureSet', 'data' : cfs, 'name' : out_id + "_to_" + pwy_en[1], 'meta' : {'original' : feature_set_id, 'ref_wsid' : ref_wsid, 'ref_net' : ref_network, 'pwy_id' :pwy_en[1]}})
      if i < 3 :
        pwy_enr_smry += pwy_en[1]+"(" + "{:6.4f}".format(float(pwy_en[0])) + ")" + nid2name[pwy_en[1]] + "\n"

    data = {'table': [header] + fields}
    meth.advance("Saving output to Workspace")

    objects.append({'type' : 'KBaseSearch.FeatureSet', 'data' : fs, 'name' : out_id, 'meta' : {'original' : feature_set_id, 'ref_wsid' : ref_wsid, 'ref_net' : ref_network, 'pwy_enr_summary' :pwy_enr_smry}})
    ws.save_objects({'workspace' : meth.workspace_id, 'objects' :objects})


    meth.advance("Returning object")
    return json.dumps(data)


@method(name="Gene network")
def gene_network(meth, nto=None):
    """This widget visualizes network objects generated by FeatureSet to Networks.

       :param nto: Network Typed Object
       :type nto: kbtypes.KBaseNetworks.Network
       :return: Rows for display
       :rtype: kbtypes.Unicode
       :output_widget: kbasePlantsNetworkNarrative

       """
    meth.stages = 1

    meth.advance("Retrieve NTO from workspace")
    if nto:
        ws = Workspace2(token=meth.token, wsid=meth.workspace_id)
        raw_data = ws.get(nto)
    else:
        raw_data = {}
    data = {'input': raw_data}
    return json.dumps(data)


# Finalize (registers service)
finalize_service()
