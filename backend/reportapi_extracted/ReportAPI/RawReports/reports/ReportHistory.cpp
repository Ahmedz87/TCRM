//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportHistory.h"
//+------------------------------------------------------------------+
//| History Raw Report                                               |
//+------------------------------------------------------------------+
BOOL CReportHistory::GenerateHTML(const ReportParams* params)
  {
   DailyReport *daily=NULL;
   int          total=0,i,result=TRUE;
   char         tmp[256]="";
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*daily))<1)  return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".date  { mso-number-format:\"yyyy\\.mm\\.dd\"; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=99%%>\n");
   fprintf(m_file,"<tr><td colspan=10><font size=2><b>%s</b> for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//--- table header
   fprintf(m_file,"<tr bgcolor=#c0c0c0 align=right>");
   fprintf(m_file,"<td align=left>Time</td><td align=left>Login</td><td>Deposit</td><td nowrap>Closed P/L</td>"
                  "<td>Balance</td><td>Credit</td><td nowrap>Floating P/L</td><td>Equity</td>"
                  "<td nowrap>Used Margin</td><td nowrap>Free Margin</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   daily=(DailyReport*)params->buffer;
   for(i=0;i<total;i++,daily++)
     {
      //--- background color
      if((i&1)==0) fprintf(m_file,"<tr align=right>");
      else         fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
      //--- row
      FormatDateTime(daily->ctm,tmp,sizeof(tmp)-1,FALSE);
      fprintf(m_file,"<td align=left class=date>%s</td>",tmp);
      fprintf(m_file,"<td align=left>%d</td>",daily->login);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->deposit      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->profit_closed,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->balance      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->credit       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->profit       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->equity       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->margin       ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->margin_free  ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportHistory::GenerateCSV(const ReportParams* params)
  {
   DailyReport *daily=NULL;
   int          total=0,i,result=TRUE;
   char         tmp[256];
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*daily))<1)  return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- report header
   fprintf(m_file,"%s for '%s' from ",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file,"%s",tmp);
   fprintf(m_file," to ");
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file,"%s",tmp);
   fprintf(m_file,"\n");
   fprintf(m_file,"Time;Login;Deposit;Closed P/L;Balance;Credit;Floating P/L;Equity;Used Margin;Free Margin\n");
//--- report rows
   daily=(DailyReport*)params->buffer;
   for(i=0;i<total;i++,daily++)
     {
      FormatDateTime(daily->ctm,tmp,sizeof(tmp)-1,FALSE);
      fprintf(m_file,"%s;%d;",tmp,daily->login);
      fprintf(m_file,"%.2lf;%.2lf;%.2lf;%.2lf;", daily->deposit,daily->profit_closed,daily->balance,daily->credit);
      fprintf(m_file,"%.2lf;%.2lf;%.2lf;%.2lf\n",daily->profit, daily->equity,       daily->margin, daily->margin_free);
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
