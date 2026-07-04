//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportCreditFacility.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReportCreditFacility::GenerateHTML(const ReportParams *params)
  {
   char   tmp[256]="";
   int    total_count=0,result=TRUE;
   double total_credit=0;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- body
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".lots  { mso-number-format:0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
                  ".date  { mso-number-format:\"yyyy\\.mm\\.dd\"; }\n"
                  ".pt0   { mso-number-format:0; }\n"
                  ".pt1   { mso-number-format:0\\.0; }\n"
                  ".pt2   { mso-number-format:0\\.00; }\n"
                  ".pt3   { mso-number-format:0\\.000; }\n"
                  ".pt4   { mso-number-format:0\\.0000; }\n"
                  ".pt5   { mso-number-format:0\\.00000; }\n"
                  ".pt6   { mso-number-format:0\\.000000; }\n"
                  ".pt7   { mso-number-format:0\\.0000000; }\n"
                  ".pt8   { mso-number-format:0\\.00000000; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"99%%\">\n");
   fprintf(m_file,"<tr><td colspan=6><font size=2><b>%s</b> for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr align=left bgcolor=\"#c0c0c0\">");
   fprintf(m_file,"<td>Deal</td><td>Login</td><td>Date</td><td nowrap>Value Date</td>"
                  "<td>Comment</td><td align=right>Amount</td></tr>\n");
//--- report rows
   TradeRecord *records=params->trades;
   for(int i=0;i<params->trades_total;i++,records++)
     {
      if(records->login<1 || records->cmd!=OP_CREDIT) continue;
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=left>");
      else                   fprintf(m_file,"<tr align=left bgcolor=\"#e0e0e0\">");
      //--- row
      fprintf(m_file,"<td>%d</td><td>%d</td>",records->order,records->login);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(records->open_time,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=date>%s</td>",FormatDateTime(records->close_time,tmp,sizeof(tmp)-1,FALSE));
      fprintf(m_file,"<td nowrap>%s</td>",records->comment);
      fprintf(m_file,"<td align=right nowrap class=money>%s</td></tr>\n",ToMoney(records->profit,2,tmp,sizeof(tmp)-1));
      //--- total
      total_credit=NormalizeDouble(total_credit+records->profit,2);
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//--- total
   fprintf(m_file,"<tr align=left bgcolor=\"#c0c0c0\"><td colspan=5><b>Total:</b></td>");
   fprintf(m_file,"<td align=right nowrap class=money><b>%s</b></td>",ToMoney(total_credit,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n</table>\n</div>\n</body></html>\n");
//--- close
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReportCreditFacility::GenerateCSV(const ReportParams *params)
  {
   char   tmp[256]="";
   int    total_count=0,result=TRUE;
   double total_credit=0;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
//--- report header
   fprintf(m_file,"%s for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE); fprintf(m_file," to %s\n",tmp);
   fprintf(m_file,"Deal;Login;Date;Value Date;Comment;Amount\n");
//--- report rows
   TradeRecord *records=params->trades;
   for(int i=0; i<params->trades_total; i++,records++)
     {
      if(records->login<1 || records->cmd!=OP_CREDIT) continue;
      //--- row
      fprintf(m_file,"%d;%d;",records->order,records->login);
      FormatDateTime(records->open_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      FormatDateTime(records->close_time,tmp,sizeof(tmp)-1,FALSE);
      fprintf(m_file,"%s;%s;%.2lf\n",tmp,records->comment,records->profit);
      //--- total
      total_credit=NormalizeDouble(total_credit+records->profit,2);
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//--- total
   fprintf(m_file,"Total:;;;;;%.2lf\n",total_credit);
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
