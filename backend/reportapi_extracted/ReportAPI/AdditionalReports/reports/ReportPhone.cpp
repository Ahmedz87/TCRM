//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportPhone.h"
//+------------------------------------------------------------------+
//| Phone Report                                                     |
//+------------------------------------------------------------------+
BOOL CReportPhone::GenerateHTML(const ReportParams* params)
  {
   char  tmp[256]="",num_fmt[32]="";
   int   i,total_count=0,result=TRUE;
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
   fprintf(m_file,"<tr><td colspan=15><font size=2><b>Phone Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//---
   fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>");
   fprintf(m_file,"<td>Deal</td><td>Login</td><td nowrap>Open Time</td><td>Type</td><td>Item</td><td>Volume</td>"
               "<td nowrap>Open Price</td><td>S/L</td><td>T/P</td><td nowrap>Close Time</td><td nowrap>Close Price</td>"
               "<td>Commission</td><td>Storage</td><td>Profit</td><td>Comment</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   TradeRecord *records=params->trades;
   for(i=0; i<params->trades_total; i++,records++)
     {
      if(records->login<1 || records->cmd>=OP_BALANCE)  continue;
      if(strcmp(records->comment,"ph")!=0 &&
         memcmp(records->comment,"ph:",3)!=0 &&
         memcmp(records->comment,"ph ",3)!=0) continue;
      //--- background color
      if((total_count&1)==0) fprintf(m_file,"<tr align=right>");
      else                   fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
      //--- price format
      if(records->digits<0 || records->digits>8) { COPY_STR(num_fmt,"class=pt4") }
      else StringCchPrintfA(num_fmt,sizeof(num_fmt)-1,"class=pt%d",records->digits);
      //--- row
      fprintf(m_file,"<td>%d</td>",records->order);
      fprintf(m_file,"<td>%d</td>",records->login);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(records->open_time,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap>%s</td>",GetCmd(records->cmd));
      strcpy(tmp,records->symbol); _strlwr(tmp);
      fprintf(m_file,"<td nowrap>%s</td>",tmp);
      fprintf(m_file,"<td nowrap>%s</td>",ToVolume(records->volume/100.0,tmp,sizeof(tmp)-1));
      ToSymExt(tmp,records->open_price,records->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      ToSym(tmp,sizeof(tmp)-1,records->sl,records->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      ToSym(tmp,sizeof(tmp)-1,records->tp,records->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      fprintf(m_file,"<td nowrap class=dt>%s</td>",FormatDateTime(records->close_time,tmp,sizeof(tmp)-1));
      ToSym(tmp,sizeof(tmp)-1,records->close_price,records->digits);
      fprintf(m_file,"<td %s>%s</td>",num_fmt,tmp);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(records->commission,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(records->storage   ,2,tmp,sizeof(tmp)-1));
      if(records->profit!=0.0)
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(records->profit ,2,tmp,sizeof(tmp)-1));
      else
         fprintf(m_file,"<td>&nbsp;</td>");
      fprintf(m_file,"<td nowrap>%s</td></tr>\n",records->comment);
      //--- total
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE;
            break;
           }
     }
//---
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportPhone::GenerateCSV(const ReportParams* params)
  {
   char  tmp[256]="";
   int   i,total_count=0,result=TRUE;
//--- checks
   if(Startup(params)==FALSE) return(FALSE);
//--- report header
   fprintf(m_file,"Phone Report for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
//---
   fprintf(m_file,"Deal;Login;Open Time;Type;Item;Volume;Open Price;S/L;T/P;Close Time;Close Price;"
                  "Commission;Storage;Profit;Comment\n");
//--- report rows
   TradeRecord *records=params->trades;
   for(i=0; i<params->trades_total; i++,records++)
     {
      if(records->login<1 || records->cmd>=OP_BALANCE) continue;
      if(strcmp(records->comment,"ph")!=0 &&
         memcmp(records->comment,"ph:",3)!=0 &&
         memcmp(records->comment,"ph ",3)!=0) continue;
      //--- row
      fprintf(m_file,"%d;",records->order);
      fprintf(m_file,"%d;",records->login);
      FormatDateTime(records->open_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%s;",GetCmd(records->cmd));
      strcpy(tmp,records->symbol); _strlwr(tmp);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%.2lf;",records->volume/100.0);
      ToSymExt(tmp,records->open_price,records->digits);
      fprintf(m_file,"%s;",tmp);
      ToSym(tmp,sizeof(tmp)-1,records->sl,records->digits);
      fprintf(m_file,"%s;",tmp);
      ToSym(tmp,sizeof(tmp)-1,records->tp,records->digits);
      fprintf(m_file,"%s;",tmp);
      FormatDateTime(records->close_time,tmp,sizeof(tmp)-1);
      fprintf(m_file,"%s;",tmp);
      ToSym(tmp,sizeof(tmp)-1,records->close_price,records->digits);
      fprintf(m_file,"%s;",tmp);
      fprintf(m_file,"%.2lf;",records->commission);
      fprintf(m_file,"%.2lf;",records->storage);
      if(records->profit!=0.00) fprintf(m_file,"%.2lf;",records->profit);
      else                               fprintf(m_file,";");
      fprintf(m_file,"\n");
      //--- total
      total_count++;
      //--- report progress and check cancellation
      if((total_count&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->trades_total)!=0)
           {
            result=FALSE;
            break;
           }
     }
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
