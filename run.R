library(knitr)
library(cegwas)
library(dplyr)
library(ggplot2)
library(jsonlite)
library(RMySQL)
library(tidyr)
library(readr)
library(xmemoise)

# Get Payload
if (length(commandArgs(trailingOnly=TRUE)) == 0) {
  args <- fromJSON('{ "trait_slug": "telomere-length", "report_slug": "test7", "trait_name" : "telomere-length"}')
} else {
  args <- fromJSON(commandArgs(trailingOnly=TRUE))
}

mysql_credentials <- fromJSON(readLines("credentials.json"))

# To connect to a database first create a src:
db <- src_mysql(dbname = "cegwas_v2", host = mysql_credentials$host, user = mysql_credentials$user, password= mysql_credentials$password)

update_status <- function(status) {
  # Update the status of the job.
  db <- src_mysql(dbname = "cegwas_v2", host = mysql_credentials$host, user = mysql_credentials$user, password= mysql_credentials$password)
  # Function for updating status of currently running job.
  comm <- sprintf("UPDATE report_trait SET status='%s' WHERE report_slug = '%s' AND trait_slug = '%s'",
                  status, args$report_slug, args$trait_slug)
  dbSendQuery(db$con, comm)
  try(invisible(dbDisconnect(db$con)), silent = T)
}

report_trait_strain_tbl <- tbl(db, "report_trait_strain_value")

# Then reference a tbl within that src
input_trait <- collect(report_trait_strain_tbl %>%
             dplyr::select(strain, report_slug, trait_slug, value) %>%
             dplyr::filter(trait_slug == args$trait_slug, report_slug == args$report_slug) %>%
             dplyr::select(strain, value))

try(invisible(dbDisconnect(db$con)), silent = T)

colnames(input_trait) <- c("strain", args$trait_slug)

output <- opts_knit$get("rmarkdown.pandoc.to")
opts_chunk$set(warning=F,
               message=F,
               echo=F,
               eval=T,
               cache=F,
               fig.path="figures/",
               cache.path="cache/",
               results="hide")

pub_theme <- ggplot2::theme_bw() +
  ggplot2::theme(axis.text.x = ggplot2::element_text(size=14, color="black"),
                 axis.text.y = ggplot2::element_text(size=14, color="black"),
                 axis.title.x = ggplot2::element_text(size=14, face="bold", color="black", vjust=-.3),
                 axis.title.y = ggplot2::element_text(size=14, face="bold", color="black", vjust=2),
                 strip.text.x = ggplot2::element_text(size=16, face="bold", color="black"),
                 strip.text.y = ggplot2::element_text(size=16, face="bold", color="black"),
                 axis.ticks= element_line( color = "black", size = 0.25), 
                 legend.position="none",
                 plot.margin = unit(c(1.0,0.5,0.5,1.0),"cm"),
                 plot.title = ggplot2::element_text(size=24, face="bold", vjust = 1),
                 legend.position="none",
                 panel.background = ggplot2::element_rect(color = "black", size= 0.75),
                 strip.background = ggplot2::element_rect(color = "black", size = 0.75)) 


opts_chunk$set(fig.width=12, fig.height=6)
output <- "html"

#=================#
# Perform Mapping #
#=================#
update_status("Processing Phenotype Data")
trait  <- process_pheno(input_trait)


# Save phenotype data
as.data.frame(t(trait[[2]])) %>% 
tibble::rownames_to_column("isotype") %>% 
plyr::rename(c("V1"=paste0("processed_",args$trait_name))) %>%
dplyr::full_join(input_trait %>% 
  dplyr::rowwise() %>%
   dplyr::mutate(isotype = cegwas::resolve_isotype(strain)[[1]])
  , by = "isotype") %>%
dplyr::select(1,3,4,2) %>%
readr::write_tsv("tables/phenotype.tsv")

update_status("Performing Mapping")

mgwas_mappings <- memoise(gwas_mappings, cache = cache_datastore(project = "andersen-lab", cache = "rcache"))

mapping <- mgwas_mappings(trait, mapping_snp_set = FALSE)

# Save mapping file
save(mapping, file = "tables/mapping.Rdata")

update_status("Processing Mapping")
pr_mapping <- dplyr::filter(mapping, log10p !=0) %>% dplyr::filter(!(grepl("MtDNA", marker) & log10p < 5))

max_sig <- max(pr_mapping$log10p) 
  
bf <- -log10(.05/nrow(pr_mapping))


proc_mappings <- data.frame()
if(max_sig > bf){
  warning("max_sig")
  proc_mappings <- process_mappings(mapping,trait) %>% 
    dplyr::filter(log10p !=0) %>% 
    dplyr::mutate(marker = gsub("_", ":", marker)) %>%
    filter(!(grepl("MtDNA",marker) & log10p < BF))
  readr::write_tsv(proc_mappings, "tables/processed_sig_mapping.tsv")
} 

mapping %>% dplyr::mutate(marker = gsub("_",":", marker)) %>%
readr::write_tsv("tables/raw_mapping.tsv")

#=====================#
# Phenotype Histogram #
#=====================#
update_status("Plotting Figures")
phenotype_data <- tidyr::gather(data.frame(trait[[2]]), strain, value)
ggplot2::ggplot(phenotype_data, aes(x = value)) +
  ggplot2::geom_histogram(color = "#0A3872", fill = "#0B5DA2") +
  ggplot2::theme_bw() +
  ggplot2::theme(axis.text.x = ggplot2::element_text(size=18, face="bold", color="black"),
                 axis.text.y = ggplot2::element_text(size=18, face="bold", color="black"),
                 axis.title.x = ggplot2::element_text(size=24, face="bold", color="black", vjust=-.3),
                 axis.title.y = ggplot2::element_text(size=24, vjust = -0.3,  color="black"),
                 strip.text.x = ggplot2::element_text(size=24, face="bold", color="black"),
                 strip.text.y = ggplot2::element_text(size=16, face="bold", color="black"),
                 plot.title = ggplot2::element_text(size=24, face="bold", vjust = 1, margin = margin(b = 20, unit = "pt")),
                 legend.position="none") +
  ggplot2::labs(x = args$trait_name, y = "Count")

ggsave("figures/phenotype_histogram-1.png", width = 10, height = 5)


#==================================#
# Manhattan Plot - Not significant #
#==================================#

if(nrow(proc_mappings) == 0){
  readr::write_tsv(pr_mapping, "tables/non_sig_mapping.tsv")
  ggplot(pr_mapping) +
  ggplot2::aes(x = POS/1e6, y = log10p) +
  ggplot2::geom_point() +
  ggplot2::facet_grid(.~CHROM, scales = "free_x", space = "free_x") +
  ggplot2::theme_bw() +
  ggplot2::geom_hline(aes(yintercept = bf), color = "#FF0000", size = 1)+
  theme_bw() +
  pub_theme + 
  theme(plot.margin = unit(c(0.0,0.5,0.5,0),"cm"),
        strip.background = element_blank(),
        axis.title.y = element_text(vjust=2.5),
        panel.border = element_rect(size=1, color = "black")) +
  ggplot2::labs(x = "Genomic Position (Mb)",
                y = expression(-log[10](p)))

  ggsave("figures/non-sig Manhattan Plot-1.png", width = 10, height = 5)

} else {

#================================================#
# Process Peaks and Manhattan Plot - Significant #
#================================================#

  peaks <- na.omit(proc_mappings) %>%
  dplyr::distinct(peak_id, .keep_all = TRUE) %>%
  dplyr::select(marker, CHROM, startPOS, endPOS, log10p, trait) %>%
  dplyr::mutate(query = paste0(CHROM, ":",startPOS, "-",endPOS)) %>%
  dplyr::arrange(desc(log10p)) %>%
  dplyr::mutate(top3peaks = seq(1:n())) %>%
  dplyr::filter(top3peaks < 4) %>%
  dplyr::select(trait,peak_pos = marker, interval = query, peak_log10p = log10p)

  # Manhattan Plot
  mplot <- cegwas::manplot(proc_mappings, "#666666")
  mplot[[1]] +
  theme_bw() +
  pub_theme + 
  theme(plot.margin = unit(c(0.0,0.5,0.5,0),"cm"),
        strip.background = element_blank(),
        #strip.text = element_blank(),
        axis.title.y = element_text(vjust=2.5),
        panel.border = element_rect(size=1, color = "black")) +
  ggplot2::labs(x = "Genomic Position (Mb)",
                y = expression(-log[10](p))) +
  theme(plot.title = ggplot2::element_blank())

  ggsave("figures/Manplot-1.png", width = 10, height = 5)


  # PxG Plot
  pg_plot <- pxg_plot(proc_mappings, color_strains = NA)
  pg_plot[[1]] +
    labs(y= args$trait_slug) +
    pub_theme + 
    theme(plot.margin = unit(c(0.0,0.5,0.5,0),"cm"),
        strip.background = element_blank(),
        #strip.text = element_blank(),
        axis.title.y = element_text(vjust=2.5),
        panel.border = element_rect(size=1, color = "black"))  +
    theme(legend.position = "none",
                      plot.title = ggplot2::element_blank())

  ggsave("figures/PxGplot-1.png", width = 10, height = 5)


  # Plot Peak LD if more than one peak.
  if(nrow(peaks) > 1){
    plot_peak_ld(proc_mappings) 
    ggsave("figures/LDplot-1.png", width = 14, height = 11)
  }

  # Get interval variants
  update_status("Fine Mapping")

  proc_variants <- function(proc_mappings) {
    process_correlations(variant_correlation(proc_mappings, quantile_cutoff_high = 0.75, quantile_cutoff_low = 0.25, condition_trait = F))
  }

  mproc_variants <- memoise(proc_variants, cache = cache_datastore(project = "andersen-lab", cache = "rcache"))

  interval_variants <- mproc_variants(proc_mappings)
  
  readr::write_tsv(interval_variants, "tables/interval_variants.tsv")
  
  # Condense Interval Variants File
  interval_variants %>% 
    dplyr::select(CHROM, POS, gene_id, num_alt_allele, num_strains, corrected_spearman_cor) %>%
    dplyr::distinct(.keep_all = T) %>%
    readr::write_tsv("tables/interval_variants_db.tsv")
}


update_status("Transferring Data")
