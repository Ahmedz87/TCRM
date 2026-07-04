//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once
//+------------------------------------------------------------------+
//| Base report class                                                |
//+------------------------------------------------------------------+
class CReport
  {
protected:
   RepGeneratorInfo  m_info;                // information about report
   FILE             *m_file;                // output file
   CReport          *m_next;                // next report

public:
                     CReport(CReport *next,LPCSTR name,LPCSTR formats=NULL);
   virtual          ~CReport();

   virtual int       Report(const ReportParams *params);
   virtual int       GenerateHTML(const ReportParams *params)=0;
   virtual int       GenerateCSV(const ReportParams *params) =0;
   int               GetInfo(const int idx,RepGeneratorInfo *info);
   inline int        Total() const { return(m_next ? m_next->Total()+1 : 1); }

protected:
   int               Startup(const ReportParams *params);
   void              WriteHeader(LPCSTR title);
  };
//+------------------------------------------------------------------+
