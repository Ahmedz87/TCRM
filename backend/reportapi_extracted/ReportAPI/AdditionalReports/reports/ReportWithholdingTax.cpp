//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportWithholdingTax.h"
//+------------------------------------------------------------------+
//| Withholding Tax Report                                           |
//+------------------------------------------------------------------+
BOOL CReportWithholdingTax::GenerateHTML(const ReportParams* params)
  {
   char   tmp[256]="";
   int    iuser,i,total_count=0,result=TRUE;
   double total_gross=.0,total_tax=.0;
   double gross,tax;
   const  UserRecord *ur=NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- body
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".lots  { mso-number-format:0\\.00; }\n"
                  ".dt    { mso-number-format:\"yyyy\\.mm\\.dd hh\\:mm\"; }\n"
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
   fprintf(m_file,"<tr><td colspan=9><font size=2><b>Withholding Tax Statement</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\">");
   fprintf(m_file,"<td>Name</td>"
                  "<td>Address</td>"
                  "<td nowrap>IRD Number</td>"
                  "<td>Status</td>"
                  "<td>Country</td>"
                  "<td align=right nowrap>Tax Rate</td>"
                  "<td align=right>Gross</td>"
                  "<td align=right>Tax</td>"
                  "<td align=right>Net</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   for(iuser=0;iuser<params->group.total;iuser++)
     {
      //--- collect data
      gross=tax=.0;
      TradeRecord *record=params->trades;
      for(i=0;i<params->trades_total;i++,record++)
        {
         if(record->login!=params->group_logins[iuser] || record->cmd!=OP_BALANCE) continue;
         //---
         if(strcmp(record->comment,"IR")==0)    gross=NormalizeDouble(gross+record->profit,2);
         if(strcmp(record->comment,"Taxes")==0) tax  =NormalizeDouble(tax  +record->profit,2);
        }
      //---
      if(gross==.0 && tax==.0) continue;
      if((ur=UserRecordGet(params,params->group_logins[iuser]))==NULL) continue;
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
      else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
      //--- row
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur->name);
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur->address);
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur->id);
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur->status);
      fprintf(m_file,"<td nowrap align=left>%s</td>",ur->country);
      fprintf(m_file,"<td class=tax>%.2lf%%</td>",ur->taxes);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(gross    ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(tax      ,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(gross+tax,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- total
      total_gross+=gross;
      total_tax  +=tax;
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,iuser,params->group.total)!=0)
           {
            result=FALSE; break;
           }
     }
//--- total
   fprintf(m_file,"<tr align=right bgcolor=\"#c0c0c0\">");
   fprintf(m_file,"<td align=left colspan=6><b>Total:</b></td>");
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_gross          ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_tax            ,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"<td nowrap class=money><b>%s</b></td>",ToMoney(total_gross+total_tax,2,tmp,sizeof(tmp)-1));
   fprintf(m_file,"</tr>\n</table>\n</div>\n</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportWithholdingTax::GenerateCSV(const ReportParams* params)
  {
   char   tmp[256]="";
   int    iuser,i,total_count=0,result=TRUE;
   double total_gross=.0,total_tax=.0;
   double gross,tax;
   const  UserRecord *ur=NULL;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
   fprintf(m_file,"Withholding Tax Statement for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
//---
   fprintf(m_file,"Name;Address;IRD Number;Status;Country;Tax Rate;Gross;Tax;Net\n");
//--- report rows
   for(iuser=0;iuser<params->group.total;iuser++)
     {
      //--- collect data
      gross=tax=.0;
      TradeRecord *record=params->trades;
      for(i=0;i<params->trades_total;i++,record++)
        {
         if(record->login!=params->group_logins[iuser] || record->cmd!=OP_BALANCE) continue;
         //---
         if(strcmp(record->comment,"IR")==0)    gross=NormalizeDouble(gross+record->profit,2);
         if(strcmp(record->comment,"Taxes")==0) tax  =NormalizeDouble(tax  +record->profit,2);
        }
      //---
      if(gross==.0 && tax==.0) continue;
      if((ur=UserRecordGet(params,params->group_logins[iuser]))==NULL) continue;
      //--- row
      fprintf(m_file,"%s;",ur->name);
      fprintf(m_file,"%s;",ur->address);
      fprintf(m_file,"%s;",ur->id);
      fprintf(m_file,"%s;",ur->status);
      fprintf(m_file,"%s;",ur->country);
      fprintf(m_file,"%.2lf%%;",ur->taxes);
      fprintf(m_file,"%.2lf;",gross);
      fprintf(m_file,"%.2lf;",tax);
      fprintf(m_file,"%.2lf\n",gross+tax);
      //--- total
      total_gross+=gross;
      total_tax  +=tax;
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,iuser,params->group.total)!=0)
           {
            result=FALSE; break;
           }
     }
//--- total
   fprintf(m_file,";;;;;Total:;");
   fprintf(m_file,"%.2lf;",total_gross);
   fprintf(m_file,"%.2lf;",total_tax);
   fprintf(m_file,"%.2lf;",total_gross+total_tax);
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
